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
import platform
import socket


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def get_pid_on_port(port: int) -> int | None:
    """获取占用指定端口的进程 PID"""
    system = platform.system()

    try:
        if system == "Windows":
            # Windows: 使用 netstat 查找占用端口的进程
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    # 提取最后一列的 PID
                    parts = line.split()
                    if parts:
                        pid = int(parts[-1])
                        return pid
        elif system == "Linux" or system == "Darwin":
            # Linux/macOS: 使用 lsof 查找
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass

    return None


def kill_process_on_port(port: int) -> bool:
    """强制终止占用指定端口的进程"""
    pid = get_pid_on_port(port)
    if pid is None:
        return False

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=5
            )
        else:
            subprocess.run(
                ["kill", "-9", str(pid)],
                capture_output=True,
                timeout=5
            )
        print(f"\033[90m[System] 监测到旧的本地服务器残留 (PID: {pid})，已强制释放 {port} 端口...\033[0m")
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def ensure_port_available(port: int) -> bool:
    """确保端口可用，如果被占用则强制释放"""
    if not is_port_in_use(port):
        return True

    print(f"\033[93m[Warning] 端口 {port} 已被占用，正在尝试释放...\033[0m")
    if kill_process_on_port(port):
        # 等待一小段时间让端口释放
        import time
        time.sleep(0.5)
        return not is_port_in_use(port)
    return False


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

    # 🆕 确保端口可用
    if not ensure_port_available(args.port):
        print(f"\033[91m[Error] 无法释放端口 {args.port}，请手动检查或使用 --port 指定其他端口。\033[0m")
        sys.exit(1)

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

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n\033[90m[System] 服务器已停止。\033[0m")
    except subprocess.CalledProcessError as e:
        print(f"\033[91m[Error] 服务器启动失败: {e}\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
