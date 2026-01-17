# agentsh + Daytona: Secure AI Agent Sandbox

This project provides a Docker image that integrates [agentsh](https://www.agentsh.org) with [Daytona](https://daytona.io) to create a secure sandbox environment for running AI agent code.

## What is agentsh?

agentsh is a policy-enforced execution gateway designed to secure AI coding agents like **Claude Code**, **Codex CLI**, and other AI-powered development tools. It intercepts and controls:

- **Commands**: Block dangerous commands like `sudo`, `su`, `ssh`
- **Network**: Block connections to malicious domains, require approval for unknown sites
- **Files**: Soft-delete protection, credential access approval
- **Environment Variables**: Protect sensitive env vars from being exposed to agents
- **DLP (Data Loss Prevention)**: Built-in redaction and tokenization to prevent sensitive data leakage

## Features

This integration provides:

| Security Layer | Protection |
|---------------|------------|
| Command blocking | `sudo`, `su`, `ssh`, `nc`, `kill`, etc. |
| Network blocking | Malicious domains (e.g., `evil.com`) |
| Network proxy | All HTTP/HTTPS traffic routed through agentsh |
| Credential protection | Approval required for `.env`, `.ssh`, `.aws` access |
| Soft-delete | File deletions are recoverable |
| Env var protection | Sensitive environment variables hidden from agents |
| DLP redaction | Automatic redaction of secrets, API keys, tokens |
| DLP tokenization | Tokenize sensitive data before it reaches AI models |

## Supported AI Coding Agents

agentsh is designed to work with:

- **Claude Code** - Anthropic's AI coding assistant
- **Codex CLI** - OpenAI's command-line coding tool
- **Aider** - AI pair programming in your terminal
- **Continue** - Open-source AI code assistant
- **Cursor** - AI-powered code editor
- Any other AI agent that executes shell commands

## Prerequisites

- Docker installed locally
- [Daytona CLI](https://www.daytona.io/docs) installed
- Daytona account with API key

## Quick Start

### 1. Clone this repository

```bash
git clone <this-repo>
cd daytona-test
```

### 2. Build the Docker image

```bash
docker build -t daytona-agentsh:v0.7.3 .
```

### 3. Test locally (optional)

```bash
# Test that evil.com is blocked
docker run --rm daytona-agentsh:v0.7.3 bash -c 'curl -s https://evil.com'
# Should show: 400 Bad Request (blocked by agentsh)

# Test that sudo is blocked
docker run --rm daytona-agentsh:v0.7.3 bash -c 'sudo whoami'
# Should fail with permission denied
```

### 4. Login to Daytona

```bash
daytona login
```

Or with API key:
```bash
daytona login --api-key YOUR_API_KEY
```

### 5. Push the image to Daytona

```bash
daytona snapshot push daytona-agentsh:v0.7.3 \
  --name "agentsh-sandbox" \
  --cpu 2 \
  --memory 2 \
  --disk 10
```

### 6. Create a sandbox

```bash
daytona sandbox create \
  --snapshot "agentsh-sandbox" \
  --name "my-secure-sandbox" \
  --auto-stop 30
```

## Using the Python SDK

Install the Daytona SDK:

```bash
pip install daytona-sdk
```

### Example: Testing Security Policies

See `example.py` for a complete example that demonstrates:
- Command blocking (sudo, su, ssh, nc)
- Network blocking (evil.com)
- Allowed operations (ls, whoami, curl to safe sites)

```bash
# Set your API key
export DAYTONA_API_KEY="your-api-key"
export DAYTONA_API_URL="https://app.daytona.io/api"

# Run the example
python example.py
```

## Policy Configuration

The security policy is defined in `default.yaml`. Key sections:

### Blocked Commands

```yaml
command_rules:
  - name: block-shell-escape
    commands: [sudo, su, chroot, nsenter, unshare]
    decision: deny

  - name: block-network-tools
    commands: [nc, netcat, ncat, socat, telnet, ssh, scp, rsync]
    decision: deny

  - name: block-system-commands
    commands: [shutdown, reboot, systemctl, kill, killall, pkill]
    decision: deny
```

### Blocked Domains

```yaml
network_rules:
  - name: block-evil-domains
    domains:
      - "evil.com"
      - "*.evil.com"
    decision: deny

  - name: block-metadata-services
    cidrs:
      - "169.254.169.254/32"  # AWS metadata
      - "100.100.100.200/32"  # Alibaba metadata
    decision: deny
```

### Allowed Package Registries

```yaml
network_rules:
  - name: allow-npm
    domains: ["registry.npmjs.org"]
    ports: [443]
    decision: allow

  - name: allow-pypi
    domains: ["pypi.org", "files.pythonhosted.org"]
    ports: [443]
    decision: allow
```

## How It Works

1. **Shell Shim**: `/bin/bash` is replaced with `agentsh-shell-shim`
2. **Auto-start**: When bash runs, agentsh server starts automatically
3. **Proxy Injection**: `HTTP_PROXY` and `HTTPS_PROXY` are set to route traffic through agentsh
4. **Policy Enforcement**: All commands and network requests are checked against the policy

```
User Login
    │
    ▼
/bin/bash (agentsh-shell-shim)
    │
    ▼
agentsh server auto-starts
    │
    ├─► Sets HTTP_PROXY, HTTPS_PROXY
    │
    ▼
Commands/Network routed through agentsh
    │
    ▼
Policy rules applied (allow/deny/approve)
```

## Customizing the Policy

Edit `default.yaml` to customize the security policy:

### Add blocked domains

```yaml
- name: block-custom-domains
  domains:
    - "malware-site.com"
    - "*.suspicious-domain.net"
  decision: deny
```

### Add blocked commands

```yaml
- name: block-custom-commands
  commands:
    - dangerous-tool
    - another-blocked-cmd
  decision: deny
```

### Require approval for sensitive operations

```yaml
- name: approve-database-access
  commands:
    - psql
    - mysql
  decision: approve
  message: "Agent wants to access database"
  timeout: 5m
```

## DLP (Data Loss Prevention)

agentsh includes built-in DLP capabilities to prevent sensitive data from being leaked to AI models. The DLP system intercepts LLM API requests and redacts sensitive data before it reaches the provider.

**Note:** DLP is configured in `config.yaml` (server config), not in `default.yaml` (policy file).

### Configuration

```yaml
dlp:
  mode: redact  # 'redact' or 'disabled'

  # Built-in pattern detection
  patterns:
    email: true
    phone: true
    credit_card: true
    ssn: true
    api_keys: true

  # Custom patterns for organization-specific data
  custom_patterns:
    - name: customer_id
      display: CUSTOMER_ID
      regex: "CUST-[0-9]{8}"

    - name: internal_token
      display: INTERNAL_TOKEN
      regex: "int_[a-zA-Z0-9]{32}"
```

### Built-in Patterns

| Pattern | Description |
|---------|-------------|
| `email` | Email addresses |
| `phone` | Phone numbers |
| `credit_card` | Credit card numbers |
| `ssn` | Social Security Numbers |
| `api_keys` | Common API key formats |

### Custom Patterns

Add organization-specific patterns with:
- `name`: Unique identifier for the pattern
- `display`: Label shown in redacted output (e.g., `[REDACTED:DISPLAY]`)
- `regex`: Regular expression to match sensitive data

See `config.yaml` for examples of custom patterns for OpenAI keys, AWS credentials, GitHub tokens, and more.

## Troubleshooting

### Commands not being blocked

Ensure you're running through the shell shim:
```bash
# Correct - runs through agentsh
docker run ... bash -c 'sudo whoami'

# Bypasses agentsh
docker run --entrypoint /bin/bash.real ... -c 'sudo whoami'
```

### Sandbox not responding / commands hanging

The agentsh daemon takes **10-20 seconds** to fully initialize after a sandbox is created. If you're using the SDK programmatically, add a wait/retry loop:

```python
# Wait for agentsh daemon to initialize
import time
import signal

for i in range(10):
    time.sleep(5)
    try:
        sandbox = daytona.get(sandbox.id)
        signal.alarm(5)  # Use signal for reliable timeout
        result = sandbox.process.exec("echo ready", timeout=5)
        signal.alarm(0)
        if result.exit_code == 0:
            print(f"Sandbox ready after {(i+1)*5}s")
            break
    except:
        signal.alarm(0)
        continue
```

See `example.py` for the complete implementation.

### Network blocking not working

Verify the proxy is set:
```bash
docker run ... bash -c 'echo $HTTPS_PROXY'
# Should show: http://127.0.0.1:<port>
```

### Viewing agentsh logs

```bash
docker run ... bash -c 'cat /var/log/agentsh/*.log'
```

## Files

| File | Description |
|------|-------------|
| `Dockerfile` | Docker image definition with agentsh v0.7.0 |
| `config.yaml` | agentsh server configuration |
| `default.yaml` | Security policy (commands, network, files, DLP) |
| `example.py` | Python SDK example demonstrating security features |

## License

MIT License - See LICENSE file for details.

## Links

- [agentsh](https://www.agentsh.org)
- [Daytona Documentation](https://www.daytona.io/docs)
- [Daytona SDK](https://pypi.org/project/daytona-sdk/)
