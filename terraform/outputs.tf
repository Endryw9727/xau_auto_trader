output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.trader.repository_url
}

output "s3_bucket_name" {
  description = "S3 bucket for reports"
  value       = aws_s3_bucket.reports.bucket
}
