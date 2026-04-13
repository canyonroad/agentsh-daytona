# agentsh + Daytona

Runtime security governance for AI agents using [agentsh](https://github.com/canyonroad/agentsh) v0.18.0 with [Daytona](https://daytona.io) sandboxes.

## Why agentsh + Daytona?

**Daytona provides isolation. agentsh provides governance.**

Daytona sandboxes give AI agents a secure, isolated compute environment. But isolation alone doesn't prevent an agent from:

- **Exfiltrating data** to unauthorized endpoints
- **Accessing cloud metadata** (AWS/GCP/Azure credentials at 169.254.169.254)
- **Leaking secrets** in outputs (API keys, tokens, PII)
- **Running dangerous commands** (sudo, ssh, kill, nc)
- **Reaching internal networks** (10.x, 172.16.x, 192.168.x)
- **Deleting workspace files** permanently

agentsh adds the governance layer that controls what agents can do inside the sandbox, providing defense-in-depth:

```
+---------------------------------------------------------+
|  Daytona Sandbox (Isolation)                            |
|  +---------------------------------------------------+  |
|  |  agentsh (Governance)                             |  |
|  |  +---------------------------------------------+  |  |
|  |  |  AI Agent                                   |  |  |
|  |  |  - Commands are policy-checked              |  |  |
|  |  |  - Network requests are filtered            |  |  |
|  |  |  - File I/O is intercepted (FUSE)           |  |  |
|  |  |  - Secrets are redacted from output         |  |  |
|  |  |  - All actions are audited                  |  |  |
|  |  +---------------------------------------------+  |  |
|  +---------------------------------------------------+  |
+---------------------------------------------------------+
```

## What agentsh Adds

| Daytona Provides | agentsh Adds |
|------------------|--------------|
| Compute isolation | Command blocking (shell shim) |
| Process sandboxing | File I/O policy (FUSE) |
| API access to sandbox | Domain allowlist/blocklist |
| Persistent environment | Cloud metadata blocking |
| | Environment variable filtering |
| | Secret detection and redaction (DLP) |
| | Bash builtin interception (BASH_ENV) |
| | Landlock execution restrictions |
| | Soft-delete file quarantine |
| | LLM request auditing |
| | Complete audit logging |

## Quick Start

### Prerequisites

- Docker installed locally
- [Daytona CLI](https://www.daytona.io/docs) installed and authenticated
- Python 3 with `pip install daytona-sdk`

### Deploy and Test

```bash
git clone https://github.com/canyonroad/agentsh-daytona
cd agentsh-daytona

# Build the image
docker build -t daytona-agentsh:v0.18.0 .

# Push as a Daytona snapshot
daytona snapshot push daytona-agentsh:v0.18.0 \
  --name "agentsh-sandbox" \
  --cpu 2 \
  --memory 2 \
  --disk 10

# Run the security demo (30+ tests)
export DAYTONA_API_KEY="your-api-key"
export DAYTONA_API_URL="https://app.daytona.io/api"
python example.py
```

## How It Works

agentsh replaces `/bin/bash` with a [shell shim](https://www.agentsh.org/docs/#shell-shim) that routes every command through the policy engine:

```
sandbox-api runs: /bin/bash -c "sudo whoami"
                     |
                     v
            +-------------------+
            |  Shell Shim       |  /bin/bash -> agentsh-shell-shim
            |  (intercepts)     |
            +--------+----------+
                     |
                     v
            +-------------------+
            |  agentsh server   |  Policy evaluation + FUSE
            |  (auto-started)   |  file interception
            +--------+----------+
                     |
              +------+------+
              v             v
        +----------+  +----------+
        |  ALLOW   |  |  BLOCK   |
        | exit: 0  |  | exit: 126|
        +----------+  +----------+
```

Every command that Daytona's sandbox-api executes is automatically intercepted -- no explicit `agentsh exec` calls needed. The `AGENTSH_SHIM_FORCE=1` environment variable ensures the shim routes through agentsh even without a TTY (Daytona runs commands via HTTP API).

## Configuration

Security policy is defined in two files:

- **`config.yaml`** -- Server configuration: network interception, [DLP patterns](https://www.agentsh.org/docs/#llm-proxy), LLM proxy, [FUSE settings](https://www.agentsh.org/docs/#fuse), [Landlock](https://www.agentsh.org/docs/#landlock), [env_inject](https://www.agentsh.org/docs/#shell-shim) (BASH_ENV for builtin blocking)
- **`default.yaml`** -- [Policy rules](https://www.agentsh.org/docs/#policy-reference): [command rules](https://www.agentsh.org/docs/#command-rules), [network rules](https://www.agentsh.org/docs/#network-rules), [file rules](https://www.agentsh.org/docs/#file-rules), [environment policy](https://www.agentsh.org/docs/#environment-policy)

See the [agentsh documentation](https://www.agentsh.org/docs/) for the full policy reference.

## Project Structure

```
agentsh-daytona/
├── Dockerfile          # Container image with agentsh v0.18.0
├── config.yaml         # Server config (FUSE, Landlock, DLP, network)
├── default.yaml        # Security policy (commands, network, files, env)
└── example.py          # Python SDK integration tests (30+ tests)
```

## Testing

The `example.py` script creates a Daytona sandbox and runs 30+ security tests across 7 categories:

- **Diagnostics** -- FUSE mount, BASH_ENV, builtin disabling, security mode
- **Blocked commands** -- sudo, su, kill
- **File access blocking** -- write to /etc, /usr/bin, /var; read /etc/shadow
- **Network blocking** -- evil.com returns 400
- **Multi-context blocking** -- env/xargs/find -exec/Python subprocess sudo
- **FUSE protection** -- cp/touch/dd/tee/mkdir to protected paths, symlink escape
- **Soft delete** -- rm quarantines to trash, agentsh trash list/restore

```bash
export DAYTONA_API_KEY="your-api-key"
export DAYTONA_API_URL="https://app.daytona.io/api"
python example.py
```

## Protection Score

agentsh v0.18.0 scores **85/100** inside a Daytona sandbox. Run `agentsh detect` inside the sandbox to see the full breakdown:

| Category | Score | Backend | What it does |
|---|---|---|---|
| **File Protection** | 25/25 | FUSE + Landlock v5 + seccomp-notify | VFS-level file interception, kernel path restrictions, soft-delete quarantine |
| **Command Control** | 25/25 | seccomp-execve | Every `execve` syscall intercepted and checked against policy |
| **Network** | 20/20 | landlock-network | TCP bind/connect filtering on all outbound connections |
| **Isolation** | 15/15 | capability-drop | All 41 Linux capabilities dropped from the permitted set |
| **Resource Limits** | 0/15 | cgroups v2 (unavailable) | CPU/memory/process limits -- blocked by cgroup permissions |

The 15 missing points are from cgroups v2. Daytona enforces resource limits at the container level (`--cpu`, `--memory`, `--disk` on snapshot push), so the actual protection is complete -- agentsh just can't claim credit for limits it doesn't control.

## For Daytona Engineers

The following sandbox runtime changes would let agentsh reach 100/100 and close remaining gaps:

### 1. Delegate a writable cgroup slice (would give +15 pts, reaching 100/100)

agentsh needs write access to a cgroup subtree to enforce per-process CPU, memory, and PID limits. Currently the parent cgroup's `subtree_control` is not writable (EACCES), and `mkdir /sys/fs/cgroup/agentsh.slice` fails.

**What to change:** Create a dedicated cgroup slice for the sandbox process and mount it writable. For example:
- Run the container with `--cgroupns=private` and delegate `+cpu +memory +pids` in `subtree_control`
- Or pre-create `/sys/fs/cgroup/agentsh.slice` owned by the sandbox user with the appropriate controllers enabled

This would let agentsh enforce `resource_limits` from the policy (max_memory_mb, cpu_quota_percent, pids_max) independently of Daytona's container-level limits -- useful for per-command and per-session granularity.

### 2. Block /proc/1/environ access (requires runtime change)

Currently readable inside the sandbox and leaks environment variables (HOSTNAME, DAYTONA_SANDBOX_ID, PATH, etc.). The test output:

```
cat /proc/1/environ | tr '\0' '\n' | head -3
PATH=/usr/local/sbin:/usr/local/bin:...
HOSTNAME=<sandbox-id>
DAYTONA_SANDBOX_ID=<sandbox-id>
```

**Why this can't be fixed from the image:** We investigated two approaches:

1. **agentsh seccomp file_monitor** (`enforce_without_fuse: true`) -- agentsh can intercept `openat` on `/proc` via seccomp-notify, but installing the seccomp filter fails because Daytona's no-new-privileges flag blocks the `seccomp()` syscall.
2. **Entrypoint chmod** -- `chmod 000 /proc/1/environ` in a root entrypoint doesn't work because `/proc` is a virtual kernel filesystem; the kernel ignores permission changes and controls access based on process ownership.

Landlock and FUSE also cannot intercept `/proc` (it's not a regular filesystem). **This requires container-level enforcement** -- either:
- Mount `/proc` with `hidepid=2` so processes can only see their own `/proc/[pid]` entries
- Or mask `/proc/1/environ` via the container runtime (Docker `--security-opt`)
- Or relax the seccomp profile to allow agentsh to install its file_monitor filter (then agentsh handles the blocking via policy)

### 3. PID namespace isolation (cosmetic, no score impact)

The sandbox currently runs in the host PID namespace. While agentsh blocks `kill`/`killall`/`pkill` via policy and capability-drop prevents actual signal delivery, a private PID namespace would be cleaner -- the agent process would be PID 1 and unable to enumerate host processes.

**What to change:** Run the sandbox container with a separate PID namespace (`--pid=private` or equivalent in the Daytona runtime).

## Related Projects

- [agentsh](https://github.com/canyonroad/agentsh) -- Runtime security for AI agents ([docs](https://www.agentsh.org/docs/))
- [Daytona](https://daytona.io) -- Sandbox infrastructure for AI agents

## License

MIT
