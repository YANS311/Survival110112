"""
start_server.py
===============
Convenience launcher for Beijing Postgraduate Simulator V2.0 (Cyber-Reality Edition).

Replaces `python manage.py runserver` with a production-grade Uvicorn ASGI server.

Usage
-----
    python start_server.py              # default: 127.0.0.1:8000, 1 worker
    python start_server.py --prod       # 0.0.0.0:8000, 2 workers, no reload
    python start_server.py --port 9000  # custom port

API docs available at: http://127.0.0.1:8000/api/docs
"""

import argparse
import subprocess
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Start the Survival110112 ASGI server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--prod", action="store_true", help="Production mode (no reload, 2 workers, 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    if args.prod:
        host    = "0.0.0.0"
        workers = 2
        reload  = False
    else:
        host    = args.host
        workers = args.workers
        reload  = args.reload

    # Resolve uvicorn path inside the venv
    venv_uvicorn = os.path.join(
        os.path.dirname(sys.executable), "uvicorn"
    )
    uvicorn_cmd = venv_uvicorn if os.path.exists(venv_uvicorn) else "uvicorn"

    # Always use the venv python that is running this script,
    # so we never accidentally pick up a different interpreter (e.g. Anaconda).
    python_exe = sys.executable

    cmd = [
        python_exe, "-m", "uvicorn",
        "core.asgi:application",
        "--host", host,
        "--port", str(args.port),
        "--log-level", "info",
    ]

    # --workers is incompatible with --reload; use one or the other.
    if reload:
        cmd.append("--reload")
    else:
        cmd += ["--workers", str(workers)]

    print("=" * 60)
    print("  Beijing Postgraduate Simulator V2.0 — Cyber-Reality Edition")
    print("=" * 60)
    print(f"  Server  : http://{host}:{args.port}")
    print(f"  API docs: http://{host}:{args.port}/api/docs")
    print(f"  Workers : {workers}")
    print(f"  Reload  : {reload}")
    print("=" * 60)
    print()

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
