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

module "agent_image" {
  source = "./modules/agent_image"

  project_name          = var.project_name
  aws_region            = var.aws_region
  aws_account_id        = data.aws_caller_identity.current.account_id
  codebuild_role_arn    = module.foundation.codebuild_role_arn
  codebuild_bucket_name = module.foundation.codebuild_bucket_name
}

module "lambda_backends" {
  source = "./modules/lambda_backends"

  project_name             = var.project_name
  solution_access_role_arn = module.foundation.solution_access_role_arn
}

module "agent_runtime" {
  source = "./modules/agent_runtime"

  project_name                  = var.project_name
  aws_region                    = var.aws_region
  ecr_image_uri                 = module.agent_image.ecr_image_uri
  solution_access_role_arn      = module.foundation.solution_access_role_arn
  product_info_kb_id            = module.knowledge_bases.product_info_kb_id
  pet_care_kb_id                = module.knowledge_bases.pet_care_kb_id
  inventory_function_name       = module.lambda_backends.inventory_function_name
  user_management_function_name = module.lambda_backends.user_management_function_name
  guardrail_id                  = module.guardrail.guardrail_id
  guardrail_version             = module.guardrail.guardrail_version
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
