"""
Starts the BusMap proxy server + a cloudflared quick tunnel.
Opens a public HTTPS URL you can visit from any phone.

Usage:
    python start_busmap_test.py [--port 8080]
"""

import argparse
import subprocess
import sys
import os
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def tail_for_url(proc, found: list):
    """Read cloudflared stderr until we see the trycloudflare URL."""
    pattern = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
    for line in proc.stderr:
        line = line.decode(errors="ignore").rstrip()
        if line:
            print(f"  [cloudflared] {line}")
        m = pattern.search(line)
        if m:
            found.append(m.group(0))
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    port = args.port

    cloudflared = os.path.join(HERE, "cloudflared")
    if not os.path.isfile(cloudflared):
        sys.exit("cloudflared binary not found. Run:\n"
                 "  curl -L https://github.com/cloudflare/cloudflared/releases/latest"
                 "/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared")

    # ── 1. Start proxy server ──────────────────────────────────────────
    proxy = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "proxy_server.py"), "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    # Give it a moment to bind
    time.sleep(1)
    if proxy.poll() is not None:
        sys.exit(f"proxy_server.py failed to start (exit {proxy.returncode})")

    print(f"✅  Proxy server started on port {port}")

    # ── 2. Start cloudflared quick tunnel ─────────────────────────────
    tunnel = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{port}",
         "--no-autoupdate"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    print("⏳  Starting cloudflared tunnel (may take ~10 s)…")
    found: list = []
    t = threading.Thread(target=tail_for_url, args=(tunnel, found), daemon=True)
    t.start()
    t.join(timeout=30)

    if not found:
        proxy.terminate()
        tunnel.terminate()
        sys.exit("Timed out waiting for cloudflared URL. Check network/firewall.")

    public_url = found[0]
    print()
    print("=" * 55)
    print(f"  🌐  Public URL (open on phone):")
    print()
    print(f"  {public_url}")
    print()
    print("  Settings panel → API Base URL → leave EMPTY")
    print("  (the proxy at /busmap-api/* handles it)")
    print("=" * 55)
    print()
    print("  Ctrl-C to stop both server and tunnel.\n")

    # ── 3. Keep alive ─────────────────────────────────────────────────
    try:
        proxy.wait()
    except KeyboardInterrupt:
        pass
    finally:
        proxy.terminate()
        tunnel.terminate()
        print("\nStopped.")


if __name__ == "__main__":
    main()
