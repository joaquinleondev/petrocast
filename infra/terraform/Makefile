BACKEND_CONFIG ?= ../../backend.config
TF_FLAGS      := -backend-config=$(BACKEND_CONFIG) -input=false

.PHONY: bootstrap plan-% apply-% destroy-% fmt validate

## bootstrap: Create S3 state bucket for remote state and native lockfiles (run once, locally)
bootstrap:
	@echo "==> Bootstrapping Terraform state backend..."
	cd bootstrap && terraform init && terraform apply
	@echo ""
	@echo "==> Copy the backend_config output above into:"
	@echo "    infra/terraform/backend.config"

## fmt: Format all .tf files
fmt:
	terraform fmt -recursive .

## validate-%: Validate a specific env (e.g. make validate-shared)
validate-%:
	cd envs/$* && terraform init $(TF_FLAGS) && terraform validate

## plan-shared / apply-shared: needs bootstrap outputs as TF_VAR_*
plan-shared apply-shared:
	@BS_BUCKET=$$(cd bootstrap && terraform output -raw state_bucket); \
	cd envs/shared && terraform init $(TF_FLAGS) && \
	  TF_VAR_tf_state_bucket_name=$$BS_BUCKET \
	  terraform $(subst -shared,,$@)

## plan-%: Plan a specific env (e.g. make plan-preview)
plan-%:
	cd envs/$* && terraform init $(TF_FLAGS) && terraform plan

## apply-%: Apply a specific env (e.g. make apply-preview)
apply-%:
	cd envs/$* && terraform init $(TF_FLAGS) && terraform apply

## apply-all: Apply shared then all envs in order
apply-all: apply-shared apply-preview apply-staging apply-prod

## destroy-%: Destroy a specific env (dangerous!)
destroy-%:
	@echo "WARNING: This will destroy all resources in envs/$*"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	cd envs/$* && terraform init $(TF_FLAGS) && terraform destroy

## output-%: Show outputs for a specific env
output-%:
	cd envs/$* && terraform init $(TF_FLAGS) && terraform output
