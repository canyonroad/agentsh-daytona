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
    print("[2] Creating sandbox from agentsh-sandbox-v29 snapshot...")
    params = CreateSandboxFromSnapshotParams(
        snapshot="agentsh-sandbox-v29",
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

        # ==================== DIAGNOSTICS ====================
        print("\n" + "=" * 60)
        print("  DIAGNOSTICS (verify security subsystems are active)")
        print("=" * 60)

        test("FUSE mounted - agentsh filesystem interception active",
             "mount | grep agentsh || echo 'FUSE NOT MOUNTED'")

        test("BASH_ENV active - builtin disabling enabled",
             "echo $BASH_ENV")

        test("kill builtin disabled - should not be a shell builtin",
             "type kill 2>&1")

        test("agentsh security mode",
             "/usr/bin/agentsh detect 2>&1 | head -10")

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

        # ==================== MULTI-CONTEXT COMMAND BLOCKING ====================
        print("\n" + "=" * 60)
        print("  MULTI-CONTEXT COMMAND BLOCKING")
        print("=" * 60)

        # Blocked commands are enforced from ANY execution context, not just shell
        # Shell shim + container no-new-privileges ensure protection across contexts

        test("env runs sudo - SHOULD BE BLOCKED",
             "env sudo whoami 2>&1")

        test("xargs spawns sudo - SHOULD BE BLOCKED",
             "echo whoami | xargs sudo 2>&1")

        test("find -exec runs sudo - SHOULD BE BLOCKED",
             "find /tmp -maxdepth 0 -exec sudo whoami \\; 2>&1")

        # Nested script running blocked command - depth-aware detection
        test("Nested script runs sudo - SHOULD BE BLOCKED",
             "echo '#!/bin/sh\nsudo whoami' > /tmp/escalate.sh && chmod +x /tmp/escalate.sh && /tmp/escalate.sh 2>&1")

        # Direct binary execution of blocked command
        test("Direct /usr/bin/sudo - SHOULD BE BLOCKED",
             "/usr/bin/sudo whoami 2>&1")

        # Python subprocess spawning blocked commands - execve intercepted
        test("Python subprocess sudo - SHOULD BE BLOCKED",
             'python3 -c "import subprocess; r=subprocess.run([\'sudo\',\'whoami\'], capture_output=True, text=True); print(r.stdout or r.stderr)" 2>&1')

        test("Python os.system kill - SHOULD BE BLOCKED",
             'python3 -c "import os; os.system(\'kill -9 1\')" 2>&1')

        # Allowed: env and Python running safe commands
        test("env runs whoami - SHOULD BE ALLOWED",
             "env whoami 2>&1")

        test("Python subprocess ls - SHOULD BE ALLOWED",
             'python3 -c "import subprocess; r=subprocess.run([\'ls\',\'/home/daytona\'], capture_output=True, text=True); print(r.stdout[:80])" 2>&1')

        # ==================== FUSE PROTECTION ====================
        print("\n" + "=" * 60)
        print("  FUSE PROTECTION (VFS-level file interception)")
        print("=" * 60)

        # FUSE intercepts file I/O at the kernel VFS level, enforcing policy
        # even when tools bypass shell redirects (cp, dd, tee, touch, mkdir)

        test("cp to /etc - SHOULD BE BLOCKED",
             "cp /etc/hosts /etc/hosts_copy 2>&1")

        test("touch /etc/newfile - SHOULD BE BLOCKED",
             "touch /etc/newfile 2>&1")

        test("dd write to /etc - SHOULD BE BLOCKED",
             "dd if=/dev/zero of=/etc/dd_test bs=1 count=1 2>&1")

        test("tee write to /usr/bin - SHOULD BE BLOCKED",
             "echo x | tee /usr/bin/evil 2>&1")

        test("mkdir in /etc - SHOULD BE BLOCKED",
             "mkdir /etc/testdir 2>&1")

        # Symlink escape: create symlink in /tmp pointing to protected file
        test("Symlink escape to /etc/shadow - SHOULD BE BLOCKED",
             "ln -sf /etc/shadow /tmp/shadow_link && cat /tmp/shadow_link 2>&1")

        # Python file I/O bypasses shell - FUSE catches at VFS level
        test("Python read /etc/shadow - SHOULD BE BLOCKED",
             'python3 -c "print(open(\'/etc/shadow\').read())" 2>&1')

        test("Python write to /etc - SHOULD BE BLOCKED",
             'python3 -c "open(\'/etc/fuse_test\',\'w\').write(\'hack\')" 2>&1')

        test("Python write to /usr/bin - SHOULD BE BLOCKED",
             'python3 -c "open(\'/usr/bin/evil\',\'w\').write(\'x\')" 2>&1')

        test("Python list /root - SHOULD BE BLOCKED",
             'python3 -c "import os; print(os.listdir(\'/root\'))" 2>&1')

        # Allowed: file I/O in workspace and /tmp
        test("cp in workspace - SHOULD BE ALLOWED",
             "echo 'original' > /home/daytona/cp_src.txt && cp /home/daytona/cp_src.txt /home/daytona/cp_dst.txt && cat /home/daytona/cp_dst.txt")

        test("touch in /tmp - SHOULD BE ALLOWED",
             "touch /tmp/fuse_test_file && ls -la /tmp/fuse_test_file 2>&1")

        test("Python write to workspace - SHOULD BE ALLOWED",
             'python3 -c "open(\'/home/daytona/py_test.txt\',\'w\').write(\'hello from python\')" && cat /home/daytona/py_test.txt')

        test("Python write to /tmp - SHOULD BE ALLOWED",
             'python3 -c "open(\'/tmp/py_test.txt\',\'w\').write(\'temp from python\')" && cat /tmp/py_test.txt')

        # ==================== SOFT DELETE ====================
        print("\n" + "=" * 60)
        print("  SOFT DELETE (recoverable file quarantine)")
        print("=" * 60)

        # Soft delete works through the FUSE workspace mount (relative paths)
        # Absolute paths bypass FUSE and hit the real filesystem directly

        test("Create file for soft-delete test",
             "echo 'important data' > soft_delete_test.txt && cat soft_delete_test.txt")

        test("rm file - SHOULD BE SOFT-DELETED (moved to trash)",
             "rm soft_delete_test.txt 2>&1 && echo 'rm exited 0'")

        test("Verify file is gone from original location",
             "ls soft_delete_test.txt 2>&1 || echo 'file gone (expected)'")

        test("agentsh trash list - SHOULD SHOW soft-deleted file",
             "/usr/bin/agentsh trash list 2>&1")

        # Get the token and restore
        test("Restore soft-deleted file via agentsh trash restore",
             "token=$(/usr/bin/agentsh trash list 2>&1 | grep soft_delete_test | head -1 | cut -f1) && "
             "/usr/bin/agentsh trash restore $token 2>&1")

        test("Verify restored file has original content",
             "cat soft_delete_test.txt 2>&1")

        # ==================== SUMMARY ====================
        print("\n" + "=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        print("""
    Security features demonstrated:

    DIAGNOSTICS:
      - FUSE mount          -> Verify agentsh VFS interception is active
      - BASH_ENV             -> Verify builtin disabling is active
      - kill builtin         -> Verify kill is not a shell builtin
      - agentsh detect       -> Verify security mode and capabilities

    BLOCKED COMMANDS:
      - sudo, su      -> Privilege escalation blocked
      - kill          -> Blocked (builtin disabled via BASH_ENV)

    FILE ACCESS BLOCKING:
      - /etc, /usr/bin, /var  -> Write denied (Landlock + FUSE + OS permissions)
      - /proc/1/environ      -> Virtual FS (requires kernel enforcement)
      - /home/daytona        -> Read/write allowed (workspace)
      - /tmp                 -> Read/write allowed (temp)

    MULTI-CONTEXT COMMAND BLOCKING:
      - env/xargs/find -exec sudo -> Blocked across contexts
      - Nested script sudo         -> Blocked in nested scripts
      - Direct /usr/bin/sudo       -> Blocked by no-new-privileges
      - Python subprocess sudo     -> Blocked from Python
      - Python os.system kill      -> Blocked from Python
      - env whoami                 -> Allowed (safe command)
      - Python subprocess ls       -> Allowed (safe command)

    FUSE PROTECTION (VFS-level file interception):
      - cp/touch/dd/tee to /etc   -> Blocked at VFS level
      - mkdir in /etc              -> Blocked at VFS level
      - Symlink escape /etc/shadow -> Path resolved, blocked
      - Python read /etc/shadow    -> Blocked at VFS level
      - Python write /etc, /usr    -> Blocked at VFS level
      - Python list /root          -> Blocked at VFS level
      - cp/Python workspace, /tmp  -> Allowed

    SOFT DELETE (recoverable file quarantine):
      - rm file in /home/daytona   -> Moved to .agentsh_trash
      - agentsh trash list         -> Shows soft-deleted files
      - agentsh trash restore      -> Restores file to original path

    BLOCKED NETWORK:
      - evil.com      -> Returns 400 Bad Request from agentsh proxy

    HOW IT WORKS:
      1. /bin/bash replaced with agentsh-shell-shim
      2. HTTPS_PROXY set to agentsh proxy
      3. BASH_ENV disables dangerous builtins (kill, enable, ulimit, etc.)
      4. Landlock restricts binary execution to system paths
      5. FUSE intercepts file I/O at VFS level
      6. Policy rules (default.yaml) enforce allow/deny
      7. All traffic routed through agentsh proxy
""")

    finally:
        print("\n[CLEANUP] Deleting sandbox...")
        daytona.delete(sandbox)
        print(f"    Sandbox {sandbox.id} deleted.")


if __name__ == "__main__":
    main()
