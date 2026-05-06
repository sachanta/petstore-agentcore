data "aws_caller_identity" "current" {}

module "foundation" {
  source = "./modules/foundation"

  project_name   = var.project_name
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  product_files      = fileset("${path.root}/../pet-store-products", "*.txt")
  product_files_path = "${path.root}/../pet-store-products"
}

module "aoss" {
  source = "./modules/aoss"

  project_name             = var.project_name
  aws_region               = var.aws_region
  aws_account_id           = data.aws_caller_identity.current.account_id
  solution_access_role_arn = module.foundation.solution_access_role_arn
  kb_execution_role_arn    = module.foundation.kb_execution_role_arn
  collection_name          = "clashofagents"
}

module "lambda_backends" {
  source = "./modules/lambda_backends"

  project_name             = var.project_name
  solution_access_role_arn = module.foundation.solution_access_role_arn
}

module "guardrail" {
  source = "./modules/guardrail"

  project_name   = var.project_name
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id
}

module "knowledge_bases" {
  source = "./modules/knowledge_bases"

  project_name             = var.project_name
  aws_region               = var.aws_region
  aws_account_id           = data.aws_caller_identity.current.account_id
  solution_access_role_arn = module.foundation.solution_access_role_arn
  kb_execution_role_arn    = module.foundation.kb_execution_role_arn
  aoss_collection_arn      = module.aoss.collection_arn
  knowledge_bucket_arn     = module.foundation.knowledge_bucket_arn
  knowledge_bucket_name    = module.foundation.knowledge_bucket_name
}
