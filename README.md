# agentsh + Daytona: Defense-in-Depth for AI Agents

This project combines [Daytona](https://daytona.io) sandbox infrastructure with [agentsh](https://www.agentsh.org) policy enforcement to create a comprehensive security solution for running AI coding agents.

## Why Both?

**Daytona** provides excellent container-level isolation—ephemeral sandboxes that prevent agents from affecting your host system. But containers alone can't distinguish between legitimate agent actions and malicious ones.

**agentsh** adds the application-level security layer that understands *what* agents are doing and enforces fine-grained policies on commands, network access, file operations, and sensitive data.

Together, they provide **defense-in-depth**: even if an AI agent is compromised or hallucinates dangerous commands, multiple security layers prevent harm.

## Security Comparison

| Threat | Daytona Alone | Daytona + agentsh |
|--------|---------------|-------------------|
| `rm -rf /` destroys data | ✅ Contained to sandbox | ✅ **Blocked** by command policy |
| Agent deletes workspace files | ❌ Files permanently lost | ✅ **Soft-deleted to trash, recoverable** |
| Agent exfiltrates secrets to `evil.com` | ❌ Network allowed | ✅ **Blocked by domain policy** |
| Agent reads `~/.aws/credentials` | ❌ File readable | ✅ **Requires approval** |
| Agent runs `sudo` for privilege escalation | ⚠️ Blocked by `no_new_privs` | ✅ **Command blocked + no_new_privs** |
| Agent accesses cloud metadata (SSRF) | ❌ `169.254.169.254` reachable | ✅ **Blocked by CIDR policy** |
| `git push --force` rewrites history | ❌ Git works normally | ✅ **Blocked by git safety rules** |
| Agent leaks API keys to LLM provider | ❌ Data sent as-is | ✅ **Redacted by DLP** |
| Agent enumerates env vars for secrets | ❌ `env` shows all | ✅ **Iteration blocked** |
| Nested script makes unauthorized request | ❌ No visibility | ✅ **Depth-aware approval** |
| Prompt injection triggers reverse shell | ⚠️ If `nc` installed | ✅ **Network tools blocked by policy** |
| Agent uses `kill` builtin to disrupt processes | ❌ Builtin bypasses interception | ✅ **Builtin disabled via BASH_ENV** |
| Python script writes to `/etc` | ❌ Depends on permissions | ✅ **Blocked by FUSE at VFS level** |
| Python script reads `/etc/shadow` | ❌ Depends on permissions | ✅ **Blocked by FUSE at VFS level** |

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
  # Deny file deletion in workspace
  - name: deny-delete-workspace
    paths: ["${PROJECT_ROOT}/**"]
    operations: [delete]
    decision: deny

  # Or use soft_delete for recoverable quarantine:
  # - name: soft-delete-workspace
  #   paths: ["${PROJECT_ROOT}/**"]
  #   operations: [delete]
  #   decision: soft_delete
  # Restore via: agentsh trash restore <token>

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

**Default blocked secrets** (automatic): AWS credentials, KUBECONFIG, GITHUB_TOKEN, LD_PRELOAD, PYTHONPATH, and more. Note: `BASH_ENV` is blocked by default in `env_policy`, but `env_inject` bypasses this to allow operator-controlled injection of the agentsh startup script.

### 4b. Environment Variable Injection (v0.8.9)

Operators can inject trusted variables that bypass policy filtering:

```yaml
# In config.yaml (under sandbox:)
sandbox:
  env_inject:
    AGENTSH_SERVER: "http://127.0.0.1:18080"
    BASH_ENV: "/usr/lib/agentsh/bash_startup.sh"
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

### 7. FUSE Filesystem Interception (v0.9.9)

FUSE provides VFS-level file interception that enforces policy rules on all file I/O, regardless of how it's invoked. This catches file operations from Python scripts, compiled binaries, and any other process — not just shell commands:

```yaml
# In config.yaml
sandbox:
  fuse:
    enabled: true
    deferred: true
    deferred_marker_file: "/dev/fuse"
    audit:
      enabled: true
      mode: "soft_delete"
      trash_path: "/home/daytona/.agentsh_trash"
```

The daytona user is added to the `fuse` group in the Dockerfile, so `/dev/fuse` is accessible without `sudo`. This avoids the `no_new_privs` restriction that blocks `sudo` in containers.

With FUSE enabled, even `python3 -c "open('/etc/shadow').read()"` is blocked by the file policy rules. Without FUSE, file access control relies solely on Landlock and OS permissions.

When `audit.mode` is set to `soft_delete`, file deletions matching `decision: soft_delete` rules are intercepted and moved to a trash directory instead of being permanently deleted. Files can be recovered via:

```bash
# List soft-deleted files
agentsh trash list

# Restore a specific file
agentsh trash restore <token>

# Purge old trash entries
agentsh trash purge --ttl 24h
```

### 8. Bash Builtin Disabling (v0.10.0)

Bash builtins like `kill`, `enable`, `ulimit`, and `umask` bypass external command interception because they execute inside the shell process itself. agentsh ships a startup script that disables these builtins:

```bash
# /usr/lib/agentsh/bash_startup.sh (installed by agentsh .deb)
enable -n kill enable ulimit umask builtin command
```

This is activated via `BASH_ENV` in the operator-controlled `env_inject` config, which bypasses `env_policy` deny rules:

```yaml
# In config.yaml (under sandbox:)
sandbox:
  env_inject:
    BASH_ENV: "/usr/lib/agentsh/bash_startup.sh"
```

Once active, `kill -9 1` will fail with "kill: not a shell builtin" instead of silently succeeding.

### 9. Landlock Filesystem Enforcement (v0.9.5)

Landlock restricts which directories allow binary execution at the kernel level:

```yaml
# In config.yaml
sandbox:
  landlock:
    enabled: true
    allow_execute:
      - /usr/bin
      - /bin
      - /usr/local/bin
      - /usr/sbin
      - /sbin
      - /usr/lib
      - /lib
    network:
      allow_connect_tcp: true
      allow_bind_tcp: true
```

This prevents executing binaries dropped into `/tmp`, `/home`, or other writable directories.

### 10. OpenTelemetry Event Export (v0.10.0)

Export audit events to an OpenTelemetry collector for centralized monitoring:

```yaml
audit:
  otel:
    enabled: true
    endpoint: "localhost:4317"
    protocol: "grpc"
    filter:
      include_categories: ["file", "process"]
      min_risk_level: "medium"
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
docker build -t daytona-agentsh:v0.10.4 .
```

### 2. Test locally

```bash
# Test that evil.com is blocked
docker run --rm daytona-agentsh:v0.10.4 bash -c 'curl -s https://evil.com'
# Output: blocked by policy (rule=block-evil-domains)

# Test that sudo is blocked
docker run --rm daytona-agentsh:v0.10.4 bash -c 'sudo whoami'
# Output: command blocked
```

### 3. Deploy to Daytona

```bash
daytona login --api-key YOUR_API_KEY

daytona snapshot push daytona-agentsh:v0.10.4 \
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
│  │  │  │  • File rules (access control, credential protection)  │    │  │  │
│  │  │  │  • Env policy (allowlist, block iteration)          │    │  │  │
│  │  │  │  • Git safety (block force push, protect main)      │    │  │  │
│  │  │  │  • DLP (redact secrets before LLM)                  │    │  │  │
│  │  │  │  • Audit logging (all operations)                   │    │  │  │
│  │  │  │  • Depth-aware policies (v0.8.1)                    │    │  │  │
│  │  │  │  • FUSE filesystem interception (v0.9.9)            │    │  │  │
│  │  │  │  • Landlock filesystem enforcement (v0.9.5)         │    │  │  │
│  │  │  │  • Bash builtin disabling via BASH_ENV (v0.10.0)    │    │  │  │
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
| `config.yaml` | agentsh server settings (logging, DLP, audit, FUSE, Landlock, BASH_ENV) |
| `default.yaml` | Security policy (commands, network, files, env) |
| `Dockerfile` | Container image with agentsh v0.10.4, python3, fuse group |
| `example.py` | Python SDK integration tests (diagnostics + security across 7 categories) |

### Key Policy Sections

**Command Rules** - What programs can run and with what arguments
**Network Rules** - Which domains/IPs are allowed, blocked, or require approval
**File Rules** - Read/write/delete permissions, soft-delete quarantine, credential protection
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

## Known Limitations

### Seccomp execve interception in containers

agentsh supports intercepting `execve` syscalls via seccomp user-notify for command policy enforcement from any execution context (not just the shell shim). However, **Daytona's container seccomp profile prevents installing custom seccomp filters**, so this feature cannot be enabled in container environments.

**Impact:** Command policy enforcement relies on the shell shim and container-level protections (e.g., `no-new-privileges`). Commands invoked through the shell shim are still fully policy-enforced. The container's own `no-new-privileges` flag independently blocks `sudo` and similar privilege escalation from all execution contexts. Bash builtins (which bypass all external interception) are handled separately via `BASH_ENV` — see [Bash Builtin Disabling](#8-bash-builtin-disabling-v0100).

**Workaround:** On hosts with full kernel access (non-containerized), enable seccomp in `config.yaml`:
```yaml
sandbox:
  seccomp:
    execve:
      enabled: true
```

### `bash_startup.sh` builtin disabling order

The `bash_startup.sh` script disables builtins using `enable -n kill enable ulimit umask builtin command`. Because `enable` itself is disabled on line 4 (before `ulimit`, `umask`, `builtin`, and `command` on subsequent lines), those later builtins may not be fully disabled in multi-line versions of the script.

**Impact:** `kill` and `enable` are reliably disabled. `ulimit`, `umask`, `builtin`, and `command` may remain active depending on the script layout. In practice, `ulimit` and `umask` are low-risk, and `builtin`/`command` are covered by the command policy rules in `default.yaml` as a secondary layer.

**Workaround:** Use a single-line `enable -n` invocation (as shown above) to disable all builtins atomically before `enable` is removed. This is the current default.

### `/proc` filesystem access in containers

agentsh's file policy rules define `deny` for `/proc/**`, but this is **not enforced in Daytona containers**. The `/proc` virtual filesystem is mounted by the kernel and is not interceptable by FUSE or (currently) by Landlock.

**Impact:** An agent can read `/proc/1/environ` and potentially discover environment variables that `env_policy` blocks from shell access. This is a gap between the command-level `env_policy` protection (which blocks `env`/`printenv` enumeration) and the filesystem-level access to the same data via `/proc`.

**Mitigation options** (in order of practicality):
1. **Container runtime**: Use `--security-opt proc=masked` or Docker's `MaskedPaths` to hide sensitive `/proc` entries (e.g., `/proc/*/environ`, `/proc/kcore`)
2. **Mount option**: Mount procfs with `hidepid=2` to restrict visibility to own processes
3. **seccomp user-notify**: agentsh could intercept `openat` syscalls and deny `/proc` paths, but this adds a context switch to every file open (high performance cost)
4. **Landlock**: Future kernel versions may improve Landlock's coverage of pseudo-filesystems

**Current status:** Daytona's container isolation prevents cross-container `/proc` access, but within the sandbox, agents can read their own process's `/proc` entries. The `env_policy.deny` list and `env_policy.block_iteration` still protect against command-level enumeration — `/proc` access is a secondary channel.

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

- **v0.10.4** - Updated to agentsh 0.10.4, performance fixes
- **v0.10.0** - Updated to agentsh 0.10.0, fixed FUSE deferred mount (removed sudo dependency, use /dev/fuse marker with fuse group), added BASH_ENV injection to disable dangerous builtins (kill, enable, ulimit), added Landlock execution path restrictions, enabled soft_delete with FUSE audit mode for recoverable file quarantine, added diagnostic tests, OpenTelemetry event export support, documented seccomp container limitation
- **v0.9.8** - Updated to agentsh 0.9.8, Landlock filesystem enforcement, file access blocking tests, changed delete policy from soft_delete to deny, documented /proc limitation
- **v0.9.2** - Updated to agentsh 0.9.2, dns_redirect and connect_redirect support
- **v0.8.10** - Updated to agentsh 0.8.10, added depth-aware command policies, env_inject support, bash builtin blocking

## Links

- [agentsh Documentation](https://www.agentsh.org)
- [Daytona Documentation](https://www.daytona.io/docs)
- [Daytona Python SDK](https://pypi.org/project/daytona-sdk/)

## License

MIT License - See LICENSE file for details.
