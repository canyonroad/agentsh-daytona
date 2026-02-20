# agentsh + Daytona

Runtime security governance for AI agents using [agentsh](https://github.com/canyonroad/agentsh) v0.10.4 with [Daytona](https://daytona.io) sandboxes.

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
docker build -t daytona-agentsh:v0.10.4 .

# Push as a Daytona snapshot
daytona snapshot push daytona-agentsh:v0.10.4 \
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
├── Dockerfile          # Container image with agentsh v0.10.4
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

## Related Projects

- [agentsh](https://github.com/canyonroad/agentsh) -- Runtime security for AI agents ([docs](https://www.agentsh.org/docs/))
- [agentsh + Blaxel](https://github.com/canyonroad/agentsh-blaxel) -- agentsh integration with Blaxel sandboxes
- [Daytona](https://daytona.io) -- Sandbox infrastructure for AI agents

## License

MIT
