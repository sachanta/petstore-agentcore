# Phase 6: Docker Image & ECR

## Goal
Build the ARM64 Docker image that packages the agent code and push it to ECR. This is the artifact that AgentCore Runtime will pull and run in Phase 7. Terraform manages the ECR repository, triggers a CodeBuild job to build + push the image, and can destroy the repository cleanly. This phase replaces notebook Steps 3–5.

---

## What We're Building

```
Dockerfile                          ← static file in repo root (replaces notebook cell-13)

terraform/
└── modules/
    └── agent_image/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

### Resources

| Resource | Name | Purpose |
|---|---|---|
| `aws_ecr_repository` | `petstore-agent-repo` | Stores Docker images for the agent. Lifecycle policy auto-expires old images. |
| `aws_ecr_lifecycle_policy` | on above repo | Keeps only the last 5 images — prevents storage cost accumulation |
| `aws_codebuild_project` | `petstore-agent-builder` | Builds the ARM64 Docker image using AWS infrastructure (no local Docker needed) |
| `null_resource` | `trigger_image_build` | Starts the CodeBuild build and waits for success before Terraform proceeds |

---

## The Dockerfile (Static File)

The notebook generated the Dockerfile dynamically in Python (cell-13). We replace that with a static `Dockerfile` committed to the repo. It does not change between deployments — the only thing that changes is the agent code it copies in.

Key contents:
```dockerfile
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim-bookworm

WORKDIR /app

COPY pet_store_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install bedrock-agentcore
RUN pip install aws-opentelemetry-distro

COPY pet_store_agent/*.py ./

ENV AWS_DEFAULT_REGION=us-east-1
ENV OTEL_PYTHON_DISTRO=aws_distro
ENV OTEL_PYTHON_CONFIGURATOR=aws_configurator
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_RESOURCE_ATTRIBUTES=service.name=petstore-agent
ENV AGENT_OBSERVABILITY_ENABLED=true

EXPOSE 8080
CMD ["opentelemetry-instrument", "python", "agentcore_entrypoint.py"]
```

Note: Environment variables for KB IDs and Lambda names are NOT baked into the image — they are injected at runtime by AgentCore (Phase 7). This makes the image reusable across environments.

---

## Why ARM64?

AgentCore Runtime runs on ARM64 (Graviton) infrastructure. If you build an AMD64 (x86) image and try to deploy it to AgentCore, the runtime will fail to start. The `--platform=linux/arm64` flag in the Dockerfile FROM line ensures the image is built for the correct architecture.

CodeBuild provides ARM_CONTAINER build environments specifically for this purpose.

---

## How CodeBuild Builds the Image

The notebook did this in Python (~150 lines). In Terraform it becomes a CodeBuild project with a buildspec defined inline:

```
Phase 1 — pre_build:
  - Authenticate Docker to ECR (aws ecr get-login-password | docker login)
  - Also authenticate to public ECR (for python:3.12-slim-bookworm base image)

Phase 2 — build:
  - docker build --platform linux/arm64 -t petstore-agent:latest .

Phase 3 — post_build:
  - docker tag petstore-agent:latest <account>.dkr.ecr.<region>.amazonaws.com/petstore-agent-repo:latest
  - docker push <account>.dkr.ecr.<region>.amazonaws.com/petstore-agent-repo:latest
```

The CodeBuild project uses:
- `ARM_CONTAINER` environment type
- `aws/codebuild/amazonlinux2-aarch64-standard:3.0` build image
- `privilegedMode: true` (required for Docker-in-Docker)
- Source: the CodeBuild staging S3 bucket (from Phase 1), populated by the `null_resource` local-exec

---

## The Build Trigger Flow

```
terraform apply
    │
    ├── aws_ecr_repository created
    ├── aws_codebuild_project created
    └── null_resource "trigger_image_build"
            │
            ├── local-exec: zip repo source + upload to S3 staging bucket
            ├── local-exec: aws codebuild start-build --project-name petstore-agent-builder
            └── local-exec: poll aws codebuild batch-get-builds until SUCCEEDED or FAILED
                    │
                    ├── SUCCEEDED → Terraform continues to Phase 7
                    └── FAILED → Terraform errors out (check CloudWatch logs)
```

Build time: typically 5-8 minutes for this image.

---

## Detecting Code Changes

A limitation of `null_resource` is that it won't re-run on subsequent `terraform apply` unless something triggers it. We use a `triggers` map with a hash of the agent source files:

```hcl
triggers = {
  agent_code_hash = sha256(join("", [
    filesha256("${path.root}/../pet_store_agent/agentcore_entrypoint.py"),
    filesha256("${path.root}/../pet_store_agent/pet_store_agent.py"),
    filesha256("${path.root}/../pet_store_agent/retrieve_product_info.py"),
    filesha256("${path.root}/../pet_store_agent/retrieve_pet_care.py"),
    filesha256("${path.root}/../pet_store_agent/inventory_management.py"),
    filesha256("${path.root}/../pet_store_agent/user_management.py"),
    filesha256("${path.root}/../Dockerfile"),
  ]))
}
```

If any agent `.py` file or the Dockerfile changes, the hash changes, the null_resource re-runs, and the image is rebuilt and pushed automatically.

---

## Destroy Behavior

```
terraform destroy
    │
    └── aws_ecr_repository destroyed
            └── force_delete = true  ← required, otherwise ECR refuses to delete a non-empty repo
```

The CodeBuild project is also destroyed. The images in ECR are deleted with the repository. No orphaned resources.

---

## Outputs (passed to Phase 7)

```
ecr_image_uri    (e.g. 040504913362.dkr.ecr.us-east-1.amazonaws.com/petstore-agent-repo:latest)
```

---

## Step-by-Step Implementation

1. Write the static `Dockerfile` at repo root (copy from the design above, adjust region)
2. Write `modules/agent_image/main.tf`
3. Wire `module "agent_image"` from root, passing codebuild bucket from Phase 1, solution role from Phase 1
4. `terraform plan` — 3 resources + 1 null_resource
5. `terraform apply` — longest step: ~8 minutes for CodeBuild
6. Verify image in ECR:
   ```bash
   aws ecr describe-images \
     --repository-name petstore-agent-repo \
     --query 'imageDetails[0].{tag:imageTags[0],pushed:imagePushedAt,size:imageSizeInBytes}'
   ```
7. `terraform destroy` — ECR repo + images deleted
8. `terraform apply` again (rebuilds image — another ~8 minutes)
9. `git push`

---

## Verify & Test

```bash
# Confirm image exists and was pushed recently
aws ecr describe-images --repository-name petstore-agent-repo

# Check CodeBuild build history
aws codebuild list-builds-for-project --project-name petstore-agent-builder

# View build logs (replace build ID)
aws codebuild batch-get-builds --ids <build-id> \
  --query 'builds[0].logs.{group:groupName,stream:streamName}'
```

---

## For Srikar's Understanding

### Homework

**1. Why ARM64 (Graviton) instead of AMD64 (x86)?**
AWS Graviton processors are ARM-based. AgentCore Runtime runs on Graviton. If you tried to run an AMD64 image on Graviton, what error would you see? AWS says Graviton instances are 20-40% cheaper and more energy efficient than equivalent x86. Why would a managed service like AgentCore default to Graviton?

**2. What is Docker-in-Docker and why does CodeBuild need `privilegedMode: true`?**
The CodeBuild environment runs a Linux container. Inside that container, we run `docker build` — which starts Docker inside Docker. Why does running Docker inside a container require elevated privileges? What security risk does this introduce?

**3. The base image is `public.ecr.aws/docker/library/python:3.12-slim-bookworm` — why ECR public, not Docker Hub?**
The original Dockerfile could have used `python:3.12-slim-bookworm` from Docker Hub. Why does the CodeBuild buildspec authenticate to ECR public registry instead? What is Docker Hub's rate limiting policy and why does it affect CI/CD pipelines?

**4. Image layers and caching — why does the Dockerfile copy `requirements.txt` separately?**
Notice the Dockerfile copies `requirements.txt` first, runs `pip install`, then copies the `.py` files. It could copy everything in one step. Why is it structured this way? What Docker layer caching behaviour does this optimise for?

**5. The `triggers` hash — what problem does it solve?**
Terraform's `null_resource` doesn't know what files it depends on unless you tell it explicitly via `triggers`. Without the file hash triggers, what would happen on `terraform apply` after you change `pet_store_agent.py`? How does Terraform decide whether to re-run a `null_resource`?
