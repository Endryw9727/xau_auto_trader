terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region
}

# EKS Cluster
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "xau-auto-trader"
  cluster_version = "1.28"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    general = {
      desired_size = 2
      min_size     = 1
      max_size     = 4

      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"

      labels = {
        workload = "general"
      }
    }

    compute = {
      desired_size = 1
      min_size     = 0
      max_size     = 2

      instance_types = ["t3.large"]
      capacity_type  = "SPOT"

      labels = {
        workload = "ml-compute"
      }

      taints = [{
        key    = "dedicated"
        value  = "ml"
        effect = "NO_SCHEDULE"
      }]
    }
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "xau-trader-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
}

# ECR Repository
resource "aws_ecr_repository" "trader" {
  name                 = "xau-auto-trader"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "trader" {
  name              = "/eks/xau-auto-trader"
  retention_in_days = 30
}

# S3 Bucket for reports backup
resource "aws_s3_bucket" "reports" {
  bucket = "xau-auto-trader-reports-${var.environment}"
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}
