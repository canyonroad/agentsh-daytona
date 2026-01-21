# agentsh + Daytona: Defense-in-Depth for AI Agents

This project combines [Daytona](https://daytona.io) sandbox infrastructure with [agentsh](https://www.agentsh.org) policy enforcement to create a comprehensive security solution for running AI coding agents.

## Why Both?

**Daytona** provides excellent container-level isolation—ephemeral sandboxes that prevent agents from affecting your host system. But containers alone can't distinguish between legitimate agent actions and malicious ones.

**agentsh** adds the application-level security layer that understands *what* agents are doing and enforces fine-grained policies on commands, network access, file operations, and sensitive data.

Together, they provide **defense-in-depth**: even if an AI agent is compromised or hallucinates dangerous commands, multiple security layers prevent harm.

## Security Comparison

| Threat | Daytona Alone | Daytona + agentsh |
|--------|---------------|-------------------|
| `rm -rf /` destroys data | ✅ Contained to sandbox | ✅ **Blocked** + files recoverable via soft-delete |
| Agent exfiltrates secrets to `evil.com` | ❌ Network allowed | ✅ **Blocked by domain policy** |
| Agent reads `~/.aws/credentials` | ❌ File readable | ✅ **Requires approval** |
| Agent runs `sudo` for privilege escalation | ⚠️ May work in container | ✅ **Command blocked** |
| Agent accesses cloud metadata (SSRF) | ❌ `169.254.169.254` reachable | ✅ **Blocked by CIDR policy** |
| `git push --force` rewrites history | ❌ Git works normally | ✅ **Blocked by git safety rules** |
| Agent leaks API keys to LLM provider | ❌ Data sent as-is | ✅ **Redacted by DLP** |
| Agent enumerates env vars for secrets | ❌ `env` shows all | ✅ **Iteration blocked** |
| Nested script makes unauthorized request | ❌ No visibility | ✅ **Depth-aware approval** |
| Prompt injection triggers reverse shell | ⚠️ `nc` may be available | ✅ **Network tools blocked** |

## What agentsh Adds to Daytona

### 1. Command Policy Enforcement

Block dangerous commands before they execute:

```yaml
command_rules:
  # Block privilege escalation
  - name: block-shell-escape
    commands: [sudo, su, chroot, nsenter, unshare]
    decision: deny

  # Block destructive operations
  - name: block-rm-recursive
    commands: [rm]
    args_patterns: ["-r", "--recursive"]
    decision: deny

  # Git safety (v0.7.10)
  - name: block-git-force-push
    commands: [git]
    args_patterns: ["push.*(--force|-f)"]
    decision: deny

  # v0.8.9: Block bash builtins that bypass seccomp
  - name: block-bash-builtins
    commands: [kill, enable, ulimit, umask, builtin, command]
    decision: deny
```

### 1b. Depth-Aware Command Policies (v0.8.1)

Distinguish between direct user commands and nested script execution:

```yaml
command_rules:
  # Allow curl when invoked directly by the agent
  - name: allow-curl-direct
    commands: [curl, wget]
    context: [direct]
    decision: allow

  # Require approval when curl is invoked from nested scripts
  - name: approve-curl-nested
    commands: [curl, wget]
    context: [nested]
    decision: approve
    message: "Nested script wants to fetch: {{.Args}}"
```

This prevents supply-chain attacks where malicious dependencies invoke network tools.

### 2. Network Domain Control

Fine-grained network policies beyond IP-level firewall rules:

```yaml
network_rules:
  # Allow package registries
  - name: allow-npm
    domains: ["registry.npmjs.org"]
    decision: allow

  # Allow code hosting
  - name: allow-github
    domains: ["github.com", "*.github.com"]
    decision: allow

  # Block cloud metadata (SSRF prevention)
  - name: block-metadata-services
    cidrs: ["169.254.169.254/32"]
    decision: deny

  # Block private networks (lateral movement)
  - name: block-private-networks
    cidrs: ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    decision: deny

  # Require approval for unknown destinations
  - name: approve-unknown-https
    ports: [443]
    decision: approve
```

### 3. File Access Controls

Protect sensitive files with approval workflows:

```yaml
file_rules:
  # Soft-delete instead of permanent deletion
  - name: soft-delete-workspace
    paths: ["${PROJECT_ROOT}/**"]
    operations: [delete]
    decision: soft_delete

  # Require approval for credential access
  - name: approve-aws-credentials
    paths: ["${HOME}/.aws/**"]
    decision: approve
    message: "Agent wants to access AWS credentials"
```

### 4. Environment Variable Protection

Control which env vars agents can see:

```yaml
env_policy:
  # Allowlist mode - only these vars pass through
  allow:
    - "HOME"
    - "PATH"
    - "TERM"
    - "NODE_ENV"
    - "CI_*"           # Glob patterns supported

  # Denylist - always blocked (in addition to default secrets)
  deny:
    - "*_SECRET*"
    - "*_TOKEN"
    - "*_KEY"

  # Limits
  max_bytes: 65536
  max_keys: 100

  # Block env/printenv enumeration
  block_iteration: true
```

**Default blocked secrets** (automatic): AWS credentials, KUBECONFIG, GITHUB_TOKEN, LD_PRELOAD, PYTHONPATH, BASH_ENV, and more.

### 4b. Environment Variable Injection (v0.8.9)

Operators can inject trusted variables that bypass policy filtering:

```yaml
# In config.yaml
env_inject:
  AGENTSH_SERVER: "http://127.0.0.1:18080"
  CUSTOM_VAR: "operator-controlled-value"
```

This ensures critical configuration reaches all processes regardless of `env_policy` restrictions.

### 5. Data Loss Prevention (DLP)

Redact secrets before they reach AI providers:

```yaml
dlp:
  mode: redact
  patterns:
    api_keys: true
    credit_card: true
  custom_patterns:
    - name: daytona_api_key
      display: DAYTONA_KEY
      regex: "dtn_[a-zA-Z0-9]{64}"
```

### 6. Comprehensive Audit Logging

Every command, file access, and network request is logged:

```yaml
audit:
  log_allowed: true
  log_denied: true
  include_stdout: true
  include_stderr: true
  retention_days: 90
```

## Supported AI Coding Agents

- **Claude Code** - Anthropic's AI coding assistant
- **Codex CLI** - OpenAI's command-line coding tool
- **Aider** - AI pair programming in your terminal
- **Continue** - Open-source AI code assistant
- **Cursor** - AI-powered code editor
- Any agent that executes shell commands

## Quick Start

### Prerequisites

- Docker installed locally
- [Daytona CLI](https://www.daytona.io/docs) installed
- Daytona account with API key

### 1. Clone and build

```bash
git clone <this-repo>
cd daytona-test
docker build -t daytona-agentsh:v0.8.10 .
```

### 2. Test locally

```bash
# Test that evil.com is blocked
docker run --rm daytona-agentsh:v0.8.10 bash -c 'curl -s https://evil.com'
# Output: blocked by policy (rule=block-evil-domains)

# Test that sudo is blocked
docker run --rm daytona-agentsh:v0.8.10 bash -c 'sudo whoami'
# Output: command blocked
```

### 3. Deploy to Daytona

```bash
daytona login --api-key YOUR_API_KEY

daytona snapshot push daytona-agentsh:v0.8.0 \
  --name "agentsh-sandbox" \
  --cpu 2 \
  --memory 2 \
  --disk 10

daytona sandbox create \
  --snapshot "agentsh-sandbox" \
  --name "my-secure-sandbox"
```

### 4. Run the security demo

```bash
pip install daytona-sdk
export DAYTONA_API_KEY="your-api-key"
python example.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Daytona Infrastructure                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Ephemeral Sandbox Container                    │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │  AI Agent (Claude Code, Cursor, Aider, etc.)                │  │  │
│  │  └──────────────────────────┬──────────────────────────────────┘  │  │
│  │                             │                                     │  │
│  │                             ▼                                     │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │  /bin/bash → agentsh-shell-shim                             │  │  │
│  │  │                                                             │  │  │
│  │  │  ┌─────────────────────────────────────────────────────┐    │  │  │
│  │  │  │           agentsh Policy Engine                     │    │  │  │
│  │  │  │                                                     │    │  │  │
│  │  │  │  • Command rules (allow/deny/approve)               │    │  │  │
│  │  │  │  • Network rules (domain/CIDR filtering)            │    │  │  │
│  │  │  │  • File rules (soft-delete, credential protection)  │    │  │  │
│  │  │  │  • Env policy (allowlist, block iteration)          │    │  │  │
│  │  │  │  • Git safety (block force push, protect main)      │    │  │  │
│  │  │  │  • DLP (redact secrets before LLM)                  │    │  │  │
│  │  │  │  • Audit logging (all operations)                   │    │  │  │
│  │  │  │  • Depth-aware policies (v0.8.1)                    │    │  │  │
│  │  │  └─────────────────────────────────────────────────────┘    │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  │                                                                   │  │
│  │  Container isolation: filesystem, network namespace, cgroups      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Daytona: Orchestration, snapshots, auto-stop, SDK access               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Security Capabilities (agentsh detect)

Running `agentsh detect` inside a Daytona sandbox shows full security features are available:

```
Platform: linux
Security Mode: full
Protection Score: 100%

CAPABILITIES
----------------------------------------
  capabilities_drop        ✓
  cgroups_v2               ✓
  ebpf                     ✓
  fuse                     ✓
  landlock                 ✓
  landlock_abi             ✓ (v5)
  landlock_network         ✓
  pid_namespace            -
  seccomp                  ✓
  seccomp_basic            ✓
  seccomp_user_notify      ✓
```

Daytona provides **100% protection score** with full security mode, including all kernel-level protections.

## Policy Configuration

### Files

| File | Purpose |
|------|---------|
| `config.yaml` | agentsh server settings (logging, DLP, audit) |
| `default.yaml` | Security policy (commands, network, files, env) |
| `Dockerfile` | Container image with agentsh v0.8.10 |
| `example.py` | Python SDK demo |

### Key Policy Sections

**Command Rules** - What programs can run and with what arguments
**Network Rules** - Which domains/IPs are allowed, blocked, or require approval
**File Rules** - Read/write/delete permissions, soft-delete, credential protection
**Env Policy** - Which environment variables are visible to agents
**Resource Limits** - Memory, CPU, process count, timeouts
**Audit** - What to log and how long to retain

### Customization Examples

#### Block a specific domain

```yaml
network_rules:
  - name: block-competitor
    domains: ["competitor.com", "*.competitor.com"]
    decision: deny
```

#### Require approval for database tools

```yaml
command_rules:
  - name: approve-database
    commands: [psql, mysql, mongosh]
    decision: approve
    message: "Agent wants to access database"
    timeout: 5m
```

#### Protect custom credential paths

```yaml
file_rules:
  - name: block-secrets-dir
    paths: ["/app/secrets/**", "**/credentials/**"]
    decision: deny
```

## Troubleshooting

### Commands not being blocked

Ensure commands run through the shell shim:
```bash
# Correct - runs through agentsh
docker run ... bash -c 'sudo whoami'

# Bypasses agentsh (don't do this)
docker run --entrypoint /bin/bash.real ... -c 'sudo whoami'
```

### Sandbox initialization delay

agentsh daemon takes 10-20 seconds to start. The `example.py` includes retry logic—see the wait loop pattern.

### Viewing logs

```bash
docker run ... bash -c 'cat /var/log/agentsh/*.log'
```

## Version History

- **v0.8.10** - Updated to agentsh 0.8.10, added depth-aware command policies, env_inject support, bash builtin blocking
- **v0.8.0** - Updated to agentsh 0.8.0, simplified security config for containers
- **v0.7.10** - Git safety rules, regex args_patterns, env protection
- **v0.7.9** - Initial Daytona integration

## Links

- [agentsh Documentation](https://www.agentsh.org)
- [Daytona Documentation](https://www.daytona.io/docs)
- [Daytona Python SDK](https://pypi.org/project/daytona-sdk/)

## License

MIT License - See LICENSE file for details.
