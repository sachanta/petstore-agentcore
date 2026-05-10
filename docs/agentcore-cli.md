# AgentCore CLI

The AgentCore CLI (`@aws/agentcore`) is an npm package for managing and interacting with Amazon Bedrock AgentCore runtimes from your terminal. It is separate from the Python SDK (`bedrock-agentcore`) that the agent container code imports at runtime.

| Tool | Package | Purpose |
|------|---------|---------|
| AgentCore CLI | `@aws/agentcore` (npm) | Deploy, invoke, inspect, and monitor runtimes from terminal |
| AgentCore SDK | `bedrock-agentcore` (pip) | Python SDK used inside the agent container code |

---

## Installation

### On the EC2 dev instance (no sudo)

```bash
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
export PATH="$HOME/.npm-global/bin:$PATH"
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc

npm install -g @aws/agentcore
agentcore --version   # 0.13.1
```

### On your Mac (no sudo)

```bash
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

npm install -g @aws/agentcore
agentcore --version
```

---

## Project initialisation

Most commands work best from a directory that has an `agentcore.json` config file. If you deployed via Terraform (as this project does), import the existing runtime rather than creating a new project:

```bash
cd /home/ubuntu/wd/repos/petstore/petstore-agentcore
agentcore import --runtime-id LangGraphAgentCoreRuntime-78qp678Xmk
```

This generates a local `agentcore.json` that points the CLI at your deployed runtime, so you don't need to pass `--runtime-id` on every command.

---

## Commands reference

### Status — what is running

```bash
agentcore status                           # interactive — shows all resources
agentcore status --type runtime-endpoint   # filter to just the runtime
agentcore status --json                    # machine-readable JSON output
```

### Invoke — send a prompt to the agent

```bash
# Interactive TUI (default)
agentcore invoke "I want to buy a Bark Park Buddy"

# Non-interactive — get raw JSON back
agentcore invoke --prompt "What cat food do you have?" --json

# Stream the response token by token
agentcore invoke --stream "Tell me about Doggy Delights"

# Send a structured payload from a file
agentcore invoke --prompt-file payload.json

# Pass a custom user ID (useful for testing subscription logic)
agentcore invoke --user-id usr_001 --prompt "CustomerId: usr_001\nI want 2 Bark Park Buddy"
```

### Logs — stream and search runtime logs

```bash
agentcore logs                             # tail live logs (interactive)
agentcore logs --since 30m                # last 30 minutes
agentcore logs --since 2h --until 1h     # time window
agentcore logs --level error              # errors only
agentcore logs --query "guardrail"        # filter by keyword
agentcore logs --json                     # output as JSON Lines
```

Logs are also in CloudWatch at `/aws/bedrock-agentcore/petstore-agent` (7-day retention).

### Traces — full ReAct reasoning chain

Each invocation produces a trace showing every LLM step, tool call, and tool response in the agent's reasoning loop.

```bash
agentcore traces list                      # list recent traces
agentcore traces get <traceId>             # download a specific trace to JSON
```

### Fetch — get runtime access info

```bash
agentcore fetch                            # prints ARN, endpoint URL, region
```

### Evals — view past evaluation results

```bash
agentcore evals                            # view saved eval results from past runs
```

---

## Full command list

```
agentcore add           Add resources to project config
agentcore create        Create a new AgentCore project
agentcore deploy        Deploy project infrastructure to AWS via CDK
agentcore dev           Launch local dev server or invoke agent locally
agentcore evals         View saved eval results from past runs
agentcore fetch         Fetch access info for deployed resources
agentcore import        Import a runtime, memory, or starter toolkit
agentcore invoke        Invoke a deployed agent endpoint
agentcore logs          Stream or search agent runtime logs
agentcore package       Package agent artifacts without deploying
agentcore pause         Pause a deployed resource
agentcore promote       Promote resources
agentcore recommendations  View recommendation history (preview)
agentcore remove        Remove resources from project config
agentcore resume        Resume a paused resource
agentcore run           Run evaluations, batch evaluations, or recommendations
agentcore status        Show deployed resource details and status
agentcore stop          Stop resources
agentcore traces        View and download agent traces
agentcore update        Check for and install CLI updates
agentcore validate      Validate agentcore/ config files
agentcore ab-test       View A/B test details and results (preview)
agentcore archive       Archive a batch evaluation or recommendation (preview)
agentcore config-bundle Manage configuration bundles (preview)
agentcore telemetry     Manage anonymous usage analytics preferences
```
