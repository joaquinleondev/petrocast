terraform {
    backend "s3" {
        key = "petrocast/bootstrap/terraform.tfstate"
    }
}
