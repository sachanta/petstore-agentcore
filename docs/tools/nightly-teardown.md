# Nightly Terraform Teardown

Automated nightly destruction of all petstore infrastructure to avoid unnecessary AWS costs outside of working hours.

## How It Works

A system crontab job runs `terraform destroy -auto-approve` every day at **8:57 PM UTC**. It tears down all 35 managed resources: ECR repo, Lambda functions, S3 buckets, OpenSearch Serverless collection, Bedrock knowledge bases, guardrail, agent runtime, CodeBuild project, IAM roles, and CloudWatch log group.

Logs are appended to `/tmp/tf-destroy.log`.

## Crontab Entry

```
57 20 * * * cd /home/ubuntu/wd/repos/petstore/petstore-agentcore/terraform && source .env && terraform destroy -auto-approve >> /tmp/tf-destroy.log 2>&1
```

| Field | Value | Meaning |
|-------|-------|---------|
| Minute | `57` | At minute 57 |
| Hour | `20` | 8 PM UTC |
| Day of month | `*` | Every day |
| Month | `*` | Every month |
| Day of week | `*` | Every day of the week |

## Prerequisites

- `cron` must be installed and running on the EC2 instance:
  ```bash
  sudo apt-get install -y cron
  sudo systemctl enable cron
  sudo systemctl start cron
  ```
- The `.env` file must exist at `terraform/.env` with the required variables:
  ```
  export TF_VAR_arize_space_id=...
  export TF_VAR_arize_api_key=...
  export TF_VAR_arize_project_name=...
  ```
- AWS credentials must be available to the `ubuntu` user (instance profile or `~/.aws/credentials`)
- Terraform must be on `$PATH`

## Managing the Cron Job

```bash
# View current crontab
crontab -l

# Edit crontab (opens in $EDITOR)
crontab -e

# Remove all cron jobs (careful!)
crontab -r

# Check cron service status
systemctl status cron
```

## Checking Logs

```bash
# View full log
cat /tmp/tf-destroy.log

# Tail last run
tail -50 /tmp/tf-destroy.log

# Check if last run succeeded (look for "Destroy complete!")
grep "Destroy complete" /tmp/tf-destroy.log | tail -1
```

## Rebuilding in the Morning

After nightly teardown, rebuild everything with:

```bash
cd /home/ubuntu/wd/repos/petstore/petstore-agentcore/terraform
source .env
terraform apply -auto-approve
```

This takes approximately 5-10 minutes and recreates all resources from scratch.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No log entries at expected time | Cron not running | `sudo systemctl start cron` |
| Log shows AWS auth errors | Instance profile expired or missing | Check `aws sts get-caller-identity` |
| Log shows "No changes" | Already destroyed or state mismatch | Run `terraform refresh` then retry |
| Partial destroy (errors) | Resource dependencies or API throttling | Re-run manually: `terraform destroy -auto-approve` |
