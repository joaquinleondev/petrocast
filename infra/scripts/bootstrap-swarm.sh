#!/bin/bash
# Terraform templatefile() — vars below are injected at apply time.
# In bash: $VAR (no braces) and $(cmd) pass through unchanged.
# To emit a literal dollar-brace in output, escape as $${VAR}.
set -euo pipefail
exec > >(tee -a /var/log/bootstrap-swarm.log) 2>&1

echo "[$(date -u)] Starting Petrocast Swarm bootstrap"

# ── Values injected by Terraform templatefile() ──────────────────────────────
AWS_REGION="${aws_region}"
ECR_REGISTRY_URL="${ecr_registry}"
ARTIFACTS_BUCKET="${artifacts_bucket}"
TRAEFIK_ACME_EMAIL="${traefik_acme_email}"
ENV="${env}"
ACME_RESOLVER="${acme_resolver}"
DOMAIN="${domain}"

# ── System dependencies ───────────────────────────────────────────────────────
# Wait for any in-progress apt operations before installing
while fuser /var/lib/dpkg/lock-frontend > /dev/null 2>&1; do
  echo "Waiting for dpkg lock..."
  sleep 2
done

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg unzip jq gettext-base less groff

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

ARCH=$(uname -m)
if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
  AWSCLI_ARCH="aarch64"
else
  AWSCLI_ARCH="x86_64"
fi
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$AWSCLI_ARCH.zip" -o /tmp/awscliv2.zip
unzip -q -u /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update

systemctl enable --now docker

# ── Docker Swarm ──────────────────────────────────────────────────────────────
# Use IMDSv2 to get private IP for swarm advertise address
IMDS_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
  "http://169.254.169.254/latest/meta-data/local-ipv4")

docker swarm init --advertise-addr "$PRIVATE_IP" 2>/dev/null || \
  echo "Swarm already initialized, skipping"

# Create overlay network shared by Traefik and app services
docker network create --driver overlay --attachable traefik-public 2>/dev/null || \
  echo "Network traefik-public already exists, skipping"

# ── ECR authentication ────────────────────────────────────────────────────────
ECR_REGISTRY=$(echo "$ECR_REGISTRY_URL" | cut -d/ -f1)
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ── Working directory ─────────────────────────────────────────────────────────
mkdir -p /opt/petrocast
chmod 755 /opt/petrocast

# ── Download Swarm stack templates and deploy scripts from S3 ────────────────
# Files are uploaded by Terraform (aws_s3_object) during envs/shared apply.
aws s3 cp "s3://$ARTIFACTS_BUCKET/swarm/" /opt/petrocast/ --recursive
aws s3 cp "s3://$ARTIFACTS_BUCKET/scripts/" /opt/petrocast/ --recursive
chmod 644 /opt/petrocast/*.yml
chmod 755 /opt/petrocast/*.sh

# ── Deploy Traefik ────────────────────────────────────────────────────────────
if [[ "$ACME_RESOLVER" == "le-dns" ]]; then
  TRAEFIK_STACK_SRC="/opt/petrocast/traefik.dns01.stack.yml"
else
  TRAEFIK_STACK_SRC="/opt/petrocast/traefik.http01.stack.yml"
fi

# Substitute only ACME_EMAIL and AWS_REGION — leave other dollar-brace patterns intact
ACME_EMAIL="$TRAEFIK_ACME_EMAIL" AWS_REGION="$AWS_REGION" \
  envsubst '$${ACME_EMAIL} $${AWS_REGION}' < "$TRAEFIK_STACK_SRC" > /tmp/traefik-rendered.yml

docker stack deploy -c /tmp/traefik-rendered.yml traefik --with-registry-auth

# Wait up to 60 s for Traefik to become ready
for i in $(seq 1 12); do
  if docker service ls --filter name=traefik_traefik --format '{{.Replicas}}' | grep -qE '^1/1$'; then
    echo "Traefik running"
    break
  fi
  echo "Waiting for Traefik replica ($i/12)..."
  sleep 5
done

echo "[$(date -u)] Bootstrap complete — env=$ENV domain=$DOMAIN"
