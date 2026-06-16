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
AWS_HOSTED_ZONE_ID="${route53_zone_id}"
# "true" only on the staging node that also runs the Phase-2 data stack.
DATA_STACK_ENABLED="${data_stack_enabled}"

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

# ── Persistent data volume (staging data stack only) ──────────────────────────
# Mount the EBS data volume at /var/lib/docker/volumes BEFORE Docker starts, so
# every named volume (postgres/dagster/metabase/datahub) lives on the snapshotted
# disk. On a restore-from-snapshot the filesystem already carries the data, so we
# only mkfs when the device is blank. `nofail` keeps boot resilient if absent.
if [[ "$DATA_STACK_ENABLED" == "true" ]]; then
  ROOT_PART=$(findmnt -no SOURCE /)
  ROOT_DISK=$(lsblk -no PKNAME "$ROOT_PART")
  DATA_DISK=$(lsblk -dn -o NAME,TYPE | awk '$2=="disk"{print $1}' | grep -v "^$ROOT_DISK$" | head -1)
  if [[ -n "$DATA_DISK" ]]; then
    DATA_DEV="/dev/$DATA_DISK"
    if ! blkid "$DATA_DEV" > /dev/null 2>&1; then
      echo "Formatting blank data volume $DATA_DEV"
      mkfs.ext4 -L petrocast-data "$DATA_DEV"
    fi
    mkdir -p /var/lib/docker/volumes
    mount "$DATA_DEV" /var/lib/docker/volumes
    grep -q "LABEL=petrocast-data" /etc/fstab || \
      echo "LABEL=petrocast-data /var/lib/docker/volumes ext4 defaults,nofail 0 2" >> /etc/fstab
    echo "Mounted $DATA_DEV at /var/lib/docker/volumes"
  else
    echo "WARNING: DATA_STACK_ENABLED but no extra data disk found"
  fi
fi

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
# Traefik file-provider dir (bind-mounted into Traefik). Empty on preview/prod;
# the data-stack bootstrap writes the basic-auth middleware here on staging.
mkdir -p /opt/petrocast/traefik-dynamic

# ── Download Swarm stack templates and deploy scripts from S3 ────────────────
# Files are uploaded by Terraform (aws_s3_object) during envs/shared apply.
aws s3 cp "s3://$ARTIFACTS_BUCKET/swarm/" /opt/petrocast/ --recursive
aws s3 cp "s3://$ARTIFACTS_BUCKET/scripts/" /opt/petrocast/ --recursive
# Phase-2 data stack bundle (compose files + init SQL + provisioning scripts).
if [[ "$DATA_STACK_ENABLED" == "true" ]]; then
  aws s3 cp "s3://$ARTIFACTS_BUCKET/stack/" /opt/petrocast/ --recursive
fi
chmod 644 /opt/petrocast/*.yml
find /opt/petrocast -name '*.sh' -exec chmod 755 {} +

# ── Deploy Traefik ────────────────────────────────────────────────────────────
if [[ "$ACME_RESOLVER" == "le-dns" ]]; then
  TRAEFIK_STACK_SRC="/opt/petrocast/traefik.dns01.stack.yml"
else
  TRAEFIK_STACK_SRC="/opt/petrocast/traefik.http01.stack.yml"
fi

# Substitute only Traefik bootstrap variables — leave other dollar-brace patterns intact
ACME_EMAIL="$TRAEFIK_ACME_EMAIL" AWS_REGION="$AWS_REGION" AWS_HOSTED_ZONE_ID="$AWS_HOSTED_ZONE_ID" \
  envsubst '$${ACME_EMAIL} $${AWS_REGION} $${AWS_HOSTED_ZONE_ID}' < "$TRAEFIK_STACK_SRC" > /tmp/traefik-rendered.yml

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

# ── Phase-2 data stack (staging only) ─────────────────────────────────────────
if [[ "$DATA_STACK_ENABLED" == "true" ]]; then
  echo "Deploying Phase-2 data stack"
  mkdir -p /etc/petrocast
  cat > /etc/petrocast/deploy-data.conf <<EOF
AWS_REGION=$AWS_REGION
ECR_REGISTRY=$ECR_REGISTRY
DOMAIN=$DOMAIN
ENV=$ENV
SSM_PATH=/petrocast/$ENV/data
COMPOSE_DIR=/opt/petrocast
EOF
  bash /opt/petrocast/deploy-data.sh up || \
    echo "WARNING: deploy-data.sh failed — see /var/log/petrocast-deploy-data.log"
fi

echo "[$(date -u)] Bootstrap complete — env=$ENV domain=$DOMAIN"
