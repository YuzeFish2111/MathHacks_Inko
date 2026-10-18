#!/usr/bin/env python3
"""Start Inko with one command:  python3 run.py   (Windows: py run.py)

First run: creates .venv and installs requirements.txt. Every run: starts the server on
your Wi-Fi and prints the address for this computer and for phones (with a QR code).

Inko sends every photo to the analysis backend, so start that first in another terminal:
    cd backend && uvicorn app.main:app --reload
(ANALYSIS_API_URL in .env if it isn't on http://127.0.0.1:8000.)

Options:
  --port 5173     use a different port
  --tunnel        also print a public https link (Cloudflare quick tunnel), so phones
                  can install Inko as an app. Needs cloudflared: brew install cloudflared
  --reload        restart automatically when server/ code changes (for development)
"""
import argparse
import atexit
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".requirements-hash"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def inside_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV.resolve()


def ensure_environment() -> None:
    """Create .venv and install requirements when missing or changed, then re-run inside it."""
    if sys.version_info < (3, 10):
        sys.exit("Inko needs Python 3.10 or newer. You have " + sys.version.split()[0])
    if not venv_python().exists():
        print("Setting up Inko for the first time (this takes a minute)...", flush=True)
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not STAMP.exists() or STAMP.read_text().strip() != wanted:
        print("Installing Python packages...", flush=True)
        py = str(venv_python())
        subprocess.check_call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
        subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)])
        STAMP.write_text(wanted)


def lan_ip() -> str | None:
    """The address other devices on this Wi-Fi can reach (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def inko_already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            return "analysis" in json.loads(r.read())
    except Exception:
        return False


def print_qr(url: str) -> None:
    """Compact QR code with explicit black and white colors, so it scans on light
    and dark terminal themes alike."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        rows = qr.get_matrix()
        if len(rows) % 2:
            rows.append([False] * len(rows[0]))
        white, black = "\033[97m", "\033[30m"
        bg_white, bg_black = "\033[107m", "\033[40m"
        for top, bottom in zip(rows[0::2], rows[1::2]):
            line = "    "
            for t, b in zip(top, bottom):
                line += (black if t else white) + (bg_black if b else bg_white) + "▀"
            print(line + "\033[0m")
    except Exception:
        pass  # the QR code is a bonus; the printed address is enough


def analysis_backend_status(url: str) -> str:
    """One line saying whether the analysis backend answers, and how to start it if not."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as r:
            version = json.loads(r.read()).get("schemaVersion")
        return f"  Analysis backend:           {url} (contract {version})"
    except Exception:
        return (f"  \033[1;33mAnalysis backend not reachable at {url}.\033[0m Photos can't be scored until it runs.\n"
                f"  Start it in another terminal:  cd backend && uvicorn app.main:app --reload")


def banner(port: int) -> None:
    from server import config
    ip = lan_ip()
    bold, dim, reset = "\033[1m", "\033[2m", "\033[0m"
    print()
    print(f"  {bold}Inko is running!{reset}")
    print()
    print(analysis_backend_status(config.ANALYSIS_API_URL))
    print()
    print(f"  On this computer:          {bold}http://localhost:{port}{reset}")
    if ip:
        print(f"  On your phone (same Wi-Fi): {bold}http://{ip}:{port}{reset}")
        print()
        print_qr(f"http://{ip}:{port}")
        print()
        print(f"  {dim}Phone can't connect? Check it's on the same Wi-Fi, and click Allow if your")
        print(f"  computer asks about incoming connections. Some school or event Wi-Fi blocks")
        print(f"  devices from seeing each other: use your phone's hotspot instead.{reset}")
    print()
    print(f"  {dim}Press Ctrl+C to stop.{reset}")
    print(flush=True)


def start_tunnel(port: int) -> None:
    """Run a Cloudflare quick tunnel (free, no account) and print its https link."""
    exe = shutil.which("cloudflared")
    if not exe:
        how = "brew install cloudflared" if sys.platform == "darwin" else "winget install --id Cloudflare.cloudflared" if os.name == "nt" else "see https://developers.cloudflare.com/cloudflared/"
        print(f"  To get an https link for installing on phones, install cloudflared first: {how}\n", flush=True)
        return
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    atexit.register(proc.terminate)

    def watch() -> None:
        for line in proc.stderr:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                print(f"\n  \033[1mSecure link (any network, installable as an app):\033[0m {url}\n", flush=True)
                print_qr(url)
                print(flush=True)
                break
        for _ in proc.stderr:  # keep draining so cloudflared never blocks
            pass

    threading.Thread(target=watch, daemon=True).start()
    print("  Starting the secure link...", flush=True)


def serve(args) -> None:
    sys.path.insert(0, str(ROOT))
    from server import config

    port = args.port or config.PORT
    if not port_is_free(port):
        if inko_already_running(port):
            print(f"\n  Inko is already running on port {port}.")
            banner(port)
            return
        for candidate in range(port + 1, port + 20):
            if port_is_free(candidate):
                print(f"  Port {port} is busy, using {candidate} instead.")
                port = candidate
                break
    banner(port)
    if args.tunnel:
        start_tunnel(port)
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, log_level="warning",
                access_log=False, reload=args.reload, reload_dirs=[str(ROOT / "server")] if args.reload else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Inko")
    parser.add_argument("--port", type=int)
    parser.add_argument("--tunnel", action="store_true")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if os.name == "nt":
        os.system("")  # turn on colors in the Windows console
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not inside_venv():
        ensure_environment()
        try:
            code = subprocess.call([str(venv_python()), str(ROOT / "run.py"), *sys.argv[1:]], cwd=ROOT)
        except KeyboardInterrupt:
            code = 0
        sys.exit(code)

    os.chdir(ROOT)
    try:
        serve(args)
    except KeyboardInterrupt:
        pass
    print("\n  Inko stopped. See you next time!\n")


if __name__ == "__main__":
    main()
