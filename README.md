# agentsh + Daytona

Runtime security governance for AI agents using [agentsh](https://github.com/canyonroad/agentsh) v0.20.2 with [Daytona](https://daytona.io) sandboxes.

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
docker build -t daytona-agentsh:v0.20.2 .

# Push as a Daytona snapshot
daytona snapshot push daytona-agentsh:v0.20.2 \
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

### Command (execve) interception in Daytona

Blocking a dangerous binary only when the shell `exec`s it directly is not enough -- it can be reached through `xargs`, `find -exec`, a nested script, or a `subprocess`. agentsh enforces policy on **every** `execve` (including descendants) using **ptrace with a seccomp `RET_TRACE` prefilter**:

- The prefilter is a small in-kernel BPF filter that traps only `execve` (everything else runs `RET_ALLOW`), so there is no per-syscall overhead, and it is inherited across `fork`/`exec` -- so when it is active it covers grandchildren spawned by `xargs`/`find`/`python`/scripts.
- agentsh's default execve backend, **seccomp user-notify** (`unix_sockets`), is intentionally **disabled here**: some Daytona runners' container seccomp profile already holds the one kernel-allowed user-notify listener, so installing a second one fails with `EBUSY`. The ptrace + `RET_TRACE` prefilter path is a basic filter (no listener), so it does not hit that conflict.

> **Honest caveat — command control is best-effort and runner-dependent.** Daytona sandboxes land on heterogeneous runners. On runners where ptrace is available, agentsh blocks direct *and* nested privilege escalation (`sudo`/`su`/`kill` via `xargs`/`find`/`python`/scripts). On runners where ptrace is **unavailable** (`agentsh detect` reports "Add SYS_PTRACE capability"), command-level enforcement degrades to the container backstop (no-new-privileges + capability-drop) and `agentsh detect` scores command control 0/25. We have also observed an occasional nested-exec leak (a `sudo` reached via `xargs` running once despite ptrace). So treat command governance in Daytona as defense-in-depth, **not** a hard guarantee. File protection, the network proxy, and soft-delete are enforced consistently across runners.

See `config.yaml` (`sandbox.ptrace` and `sandbox.seccomp.shellc.opaque`) for the exact settings and rationale.

## Configuration

Security policy is defined in two files:

- **`config.yaml`** -- Server configuration: network interception, [DLP patterns](https://www.agentsh.org/docs/#llm-proxy), LLM proxy, [FUSE settings](https://www.agentsh.org/docs/#fuse), [Landlock](https://www.agentsh.org/docs/#landlock), [env_inject](https://www.agentsh.org/docs/#shell-shim) (BASH_ENV for builtin blocking), and `sandbox.ptrace` execve interception (with the seccomp `RET_TRACE` prefilter; see "Command (execve) interception in Daytona" above)
- **`default.yaml`** -- [Policy rules](https://www.agentsh.org/docs/#policy-reference): [command rules](https://www.agentsh.org/docs/#command-rules), [network rules](https://www.agentsh.org/docs/#network-rules), [file rules](https://www.agentsh.org/docs/#file-rules), [environment policy](https://www.agentsh.org/docs/#environment-policy)

See the [agentsh documentation](https://www.agentsh.org/docs/) for the full policy reference.

## Project Structure

```
agentsh-daytona/
├── Dockerfile          # Container image with agentsh v0.20.2
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

agentsh scores **up to 85/100** inside a Daytona sandbox, but the score is **runner-dependent** (see the note below). The breakdown below is from a runner where ptrace is available; run `agentsh detect` inside your own sandbox to see its actual numbers:

| Category | Score | Backend | What it does |
|---|---|---|---|
| **File Protection** | 25/25 | FUSE + Landlock v5 | VFS-level file interception, kernel path restrictions, soft-delete quarantine |
| **Command Control** | 0–25/25 | ptrace + seccomp `RET_TRACE` prefilter | `execve` (and descendants) checked against policy **when ptrace is available**; 0/25 on runners where it isn't |
| **Network** | 20/20 | landlock-network | TCP bind/connect filtering on all outbound connections |
| **Isolation** | 15/15 | capability-drop | All 41 Linux capabilities dropped from the permitted set |
| **Resource Limits** | 0/15 | cgroups v2 (unavailable) | CPU/memory/process limits -- blocked by cgroup permissions |

The 15 missing points are from cgroups v2. Daytona enforces resource limits at the container level (`--cpu`, `--memory`, `--disk` on snapshot push), so the actual protection is complete -- agentsh just can't claim credit for limits it doesn't control.

> **The score and command-control backend vary by Daytona runner.** Different sandboxes land on different runners: some have ptrace available (command control ~25/25, score ~85/100), and some don't (`agentsh detect` reports "Add SYS_PTRACE capability", command control 0/25, score ~60/100). `detect` may also label the command backend `seccomp-execve` or `ptrace`, and report seccomp as available or `EBUSY`, depending on the runner (the seccomp/ptrace probe accuracy is also affected by a known scoring bug). **File protection, network, and soft-delete are enforced consistently across runners; command governance is best-effort** -- see the caveat under "Command (execve) interception in Daytona".

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

1. **agentsh seccomp file_monitor** (`enforce_without_fuse: true`) -- agentsh can intercept `openat` on `/proc` via seccomp user-notify. (Correction to an earlier diagnosis: the `seccomp()` syscall is **not** blocked by no-new-privileges. `no_new_privs` is actually `0` in the sandbox, and a basic seccomp filter installs fine once agentsh sets `no_new_privs=1` first. The real obstacle is that the user-notify **listener** the file_monitor needs returns `EBUSY` on runners whose container seccomp profile already holds the one kernel-allowed user-notify listener -- so it is not reliable across Daytona runners. Command/`execve` enforcement sidesteps this by using ptrace + a `RET_TRACE` prefilter, which is not a listener; but `/proc` `openat` interception via file_monitor still depends on the user-notify listener.)
2. **Entrypoint chmod** -- `chmod 000 /proc/1/environ` in a root entrypoint doesn't work because `/proc` is a virtual kernel filesystem; the kernel ignores permission changes and controls access based on process ownership.

Landlock and FUSE also cannot intercept `/proc` (it's not a regular filesystem). **This requires container-level enforcement** -- either:
- Mount `/proc` with `hidepid=2` so processes can only see their own `/proc/[pid]` entries
- Or mask `/proc/1/environ` via the container runtime (Docker `--security-opt`)
- Or ensure no container-level user-notify seccomp listener is installed on the runner, so agentsh's file_monitor listener can attach (then agentsh handles the blocking via policy)

### 3. PID namespace isolation (cosmetic, no score impact)

The sandbox currently runs in the host PID namespace. While agentsh blocks `kill`/`killall`/`pkill` via policy and capability-drop prevents actual signal delivery, a private PID namespace would be cleaner -- the agent process would be PID 1 and unable to enumerate host processes.

**What to change:** Run the sandbox container with a separate PID namespace (`--pid=private` or equivalent in the Daytona runtime).

## Related Projects

- [agentsh](https://github.com/canyonroad/agentsh) -- Runtime security for AI agents ([docs](https://www.agentsh.org/docs/))
- [Daytona](https://daytona.io) -- Sandbox infrastructure for AI agents

## License

MIT
