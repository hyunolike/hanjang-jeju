"""엔진 실행 진입점.

- 프로그램 창(Windows WPF, Mac Photino)이 숨김으로 켜고 끈다: jeju-engine --port 8765 --parent-pid 1234
- 웹 브라우저로 바로 쓰기: jeju-engine --open  (빈 포트를 골라 켜고 기본 브라우저로 연다)

127.0.0.1에만 열고 외부 주소를 부르지 않는다.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _watch_parent(pid: int) -> None:
    """부모 프로그램이 끝나면 엔진도 끝낸다. 비정상 종료 때 엔진이 남지 않게 한다."""
    while True:
        time.sleep(2)
        try:
            os.kill(pid, 0)
        except OSError:
            os._exit(0)


def _open_when_ready(url: str) -> None:
    for _ in range(240):
        try:
            urllib.request.urlopen(f"{url}api/health", timeout=1)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.5)


def main() -> None:
    # 묶은 실행 파일에서 보조 프로세스가 이 진입점을 다시 부를 때 처리한다.
    multiprocessing.freeze_support()
    if any(arg in sys.argv for arg in ("-c", "-B", "-S", "-I")) and "--port" not in sys.argv and "--open" not in sys.argv:
        return
    parser = argparse.ArgumentParser(description="한 장 제주 분석 엔진")
    parser.add_argument("--port", type=int, default=0, help="0이면 빈 포트를 고른다")
    parser.add_argument("--open", action="store_true", help="준비되면 기본 웹 브라우저로 연다")
    parser.add_argument("--parent-pid", type=int, default=0, help="이 프로세스가 끝나면 엔진도 끝낸다")
    args = parser.parse_args()
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}/"

    if args.parent_pid and os.name != "nt":
        threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()
    if args.open:
        print(f"한 장 제주: {url} 에서 열려요. 이 창을 닫으면 끝나요.", flush=True)
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    from jeju_agent.api import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
