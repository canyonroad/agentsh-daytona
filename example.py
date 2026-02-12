#!/usr/bin/env python3
"""
agentsh + Daytona Security Demo

This script demonstrates the security features of agentsh running in a Daytona sandbox.

Prerequisites:
    pip install daytona-sdk

Usage:
    export DAYTONA_API_KEY="your-api-key"
    export DAYTONA_API_URL="https://app.daytona.io/api"
    python example.py
"""

import os
import sys
import time
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Command timed out")

def main():
    # Check for API key
    if not os.environ.get("DAYTONA_API_KEY"):
        print("Error: DAYTONA_API_KEY environment variable not set")
        sys.exit(1)

    from daytona_sdk import Daytona
    from daytona_sdk.common.daytona import CreateSandboxFromSnapshotParams

    print("=" * 60)
    print("  agentsh + Daytona Security Demo")
    print("=" * 60)

    # Initialize Daytona client
    print("\n[1] Connecting to Daytona...")
    daytona = Daytona()

    # Create sandbox
    print("[2] Creating sandbox from agentsh-sandbox-v16 snapshot...")
    params = CreateSandboxFromSnapshotParams(
        snapshot="agentsh-sandbox-v16",
        auto_stop_interval=30
    )
    sandbox = daytona.create(params=params, timeout=120)
    print(f"    Sandbox ID: {sandbox.id}")

    # Wait for agentsh daemon to initialize (takes ~20s after container start)
    print("[3] Waiting for agentsh daemon to initialize...")
    sys.stdout.flush()

    # Retry loop to check if sandbox is ready (using signal for reliable timeout)
    signal.signal(signal.SIGALRM, timeout_handler)
    max_retries = 10
    retry_interval = 5
    sandbox_ready = False

    for i in range(max_retries):
        time.sleep(retry_interval)
        try:
            # Re-fetch sandbox and try a simple command with signal timeout
            sandbox = daytona.get(sandbox.id)
            signal.alarm(5)  # 5 second timeout
            result = sandbox.process.exec("echo ready", timeout=5)
            signal.alarm(0)  # Cancel alarm
            if result.exit_code == 0:
                print(f"    Sandbox ready after {(i+1)*retry_interval}s")
                sandbox_ready = True
                break
        except TimeoutError:
            signal.alarm(0)
            print(f"    Waiting... ({(i+1)*retry_interval}s)")
            sys.stdout.flush()
        except Exception as e:
            signal.alarm(0)
            print(f"    Error: {e} - retrying...")
            sys.stdout.flush()

    if not sandbox_ready:
        print("    Warning: Sandbox may not be fully ready after 50s")

    try:
        # Helper function with signal-based timeout
        def test(description, command):
            print(f"\n[TEST] {description}")
            print(f"       Command: {command}")
            sys.stdout.flush()
            try:
                signal.alarm(30)  # 30 second timeout
                result = sandbox.process.exec(command, timeout=30)
                signal.alarm(0)
                output = result.result.strip() if result.result else "(no output)"
                # Truncate long output
                if len(output) > 150:
                    output = output[:150] + "..."
                print(f"       Output: {output}")
                print(f"       Exit code: {result.exit_code}")
                return result.exit_code
            except TimeoutError:
                signal.alarm(0)
                print(f"       Error: Command timed out after 30s")
                return -1
            except Exception as e:
                signal.alarm(0)
                print(f"       Error: {e}")
                return -1

        # ==================== ALLOWED OPERATIONS ====================
        print("\n" + "=" * 60)
        print("  ALLOWED OPERATIONS")
        print("=" * 60)

        test("whoami - Current user", "whoami")
        test("id - User info", "id")
        test("pwd - Working directory", "pwd")
        test("ls - List files", "ls -la /home/daytona | head -5")
        test("agentsh version", "/usr/bin/agentsh --version")
        test("HTTPS_PROXY is set", "echo $HTTPS_PROXY")

        # ==================== BLOCKED COMMANDS ====================
        print("\n" + "=" * 60)
        print("  BLOCKED COMMANDS")
        print("=" * 60)

        test("sudo whoami - SHOULD BE BLOCKED", "sudo whoami 2>&1")
        test("su root - SHOULD BE BLOCKED", "su root -c whoami 2>&1")
        test("kill -9 1 - SHOULD BE BLOCKED", "kill -9 1 2>&1")

        # ==================== FILE ACCESS BLOCKING ====================
        print("\n" + "=" * 60)
        print("  FILE ACCESS BLOCKING")
        print("=" * 60)

        # Allowed: write to workspace
        test("Write to workspace - SHOULD BE ALLOWED",
             "echo 'hello' > /home/daytona/test_write.txt && cat /home/daytona/test_write.txt")

        # Allowed: read from workspace
        test("Read from workspace - SHOULD BE ALLOWED",
             "cat /home/daytona/test_write.txt")

        # Blocked: write to /etc
        test("Write to /etc/test - SHOULD BE BLOCKED",
             "echo 'hack' > /etc/test_file 2>&1")

        # Blocked: read /proc/1/environ
        # Note: /proc is a virtual kernel filesystem - blocking depends on
        # kernel-level enforcement (Landlock) or container isolation
        test("Read /proc/1/environ - may leak env vars in containers",
             "cat /proc/1/environ 2>&1 | tr '\\0' '\\n' | head -3")

        # Blocked: write to system bin directory
        test("Write to /usr/bin - SHOULD BE BLOCKED",
             "echo 'x' > /usr/bin/evil 2>&1")

        # Blocked: create file outside allowed paths
        test("Write to /var/evil - SHOULD BE BLOCKED",
             "echo 'x' > /var/evil 2>&1")

        # Allowed: read system binaries (read-only access)
        test("Read /usr/bin/ls (stat) - SHOULD BE ALLOWED",
             "ls -la /usr/bin/ls 2>&1")

        # Allowed: write to /tmp
        test("Write to /tmp - SHOULD BE ALLOWED",
             "echo 'temp' > /tmp/test_file.txt && cat /tmp/test_file.txt")

        # ==================== NETWORK BLOCKING ====================
        print("\n" + "=" * 60)
        print("  NETWORK BLOCKING")
        print("=" * 60)

        test("curl evil.com - SHOULD BE BLOCKED (400)",
             "curl -s -v https://evil.com 2>&1 | grep -E '(400|Bad Request|CONNECT)'")

        test("curl evil.com HTTP status",
             "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 https://evil.com 2>&1")

        # ==================== SUMMARY ====================
        print("\n" + "=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        print("""
    Security features demonstrated:

    BLOCKED COMMANDS:
      - sudo, su      -> Privilege escalation blocked
      - kill          -> System commands blocked

    FILE ACCESS BLOCKING:
      - /etc, /usr/bin, /var  -> Write denied (Landlock + OS permissions)
      - /proc/1/environ      -> Virtual FS (requires kernel enforcement)
      - /home/daytona        -> Read/write allowed (workspace)
      - /tmp                 -> Read/write allowed (temp)

    BLOCKED NETWORK:
      - evil.com      -> Returns 400 Bad Request from agentsh proxy

    HOW IT WORKS:
      1. /bin/bash replaced with agentsh-shell-shim
      2. HTTPS_PROXY set to agentsh proxy
      3. All traffic routed through agentsh
      4. Policy rules (default.yaml) enforce allow/deny
      5. Landlock (v0.9.5+) adds kernel-level filesystem enforcement
""")

    finally:
        print("\n[CLEANUP] Deleting sandbox...")
        daytona.delete(sandbox)
        print(f"    Sandbox {sandbox.id} deleted.")


if __name__ == "__main__":
    main()
