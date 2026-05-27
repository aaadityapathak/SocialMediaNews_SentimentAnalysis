# Define required providers
terraform {
  required_version = "~> 1.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 1.53"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
  backend "http" {}
}

# Configure the OpenStack Provider via environment variables
provider "openstack" {}

provider "kubernetes" {
  # Kubeconfig file must be placed in this directory
  config_path = "${path.module}/config"
}

provider "helm" {
  kubernetes = {
    config_path = "${path.module}/config"
  }
}
