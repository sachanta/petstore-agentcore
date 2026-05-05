data "aws_caller_identity" "current" {}

module "foundation" {
  source = "./modules/foundation"

  project_name   = var.project_name
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  product_files = fileset("${path.root}/../pet-store-products", "*.txt")
  product_files_path = "${path.root}/../pet-store-products"
}
