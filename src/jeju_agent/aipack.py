"""오프라인 AI 팩: llama.cpp 서버와 모델 파일을 찾아 엔진이 켜고 끈다 (명세 M01–M04).

팩 폴더 구조(팩 설치 파일이 만든다):

    ai-pack.json             {"format": 1, "name": ..., "model": "models/....gguf", "model_size": N,
                              "server": "llama/llama-server(.exe)", "llama_cpp": "b12052"}
    llama/llama-server(.exe) llama.cpp 서버와 라이브러리
    models/*.gguf            모델
    licenses/                llama.cpp(MIT), Qwen3(Apache-2.0) 라이선스

찾는 순서: 환경 변수 JEJU_AI_PACK(값이 off면 쓰지 않음) → 운영체제별 기본 위치.
서버는 127.0.0.1의 빈 포트에만 열고, 실행마다 새로 만든 API 키(환경 변수로 전달)가 있어야 응답한다.
Windows에서는 Job Object에 묶어 엔진이 어떻게 끝나든 서버가 남지 않게 한다.
"""

from __future__ import annotations

import atexit
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MANIFEST = "ai-pack.json"
FORMAT = 1
START_ATTEMPTS = 2  # 빈 포트를 고른 뒤 다른 프로그램이 먼저 잡으면 서버가 바로 끝난다. 새 포트로 한 번 더 켠다.
EARLY_EXIT_SECONDS = 1.5

# 로컬 서버만 부르므로 프록시를 쓰지 않는다(llm._OPENER와 같은 이유).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class PackError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pack:
    root: Path
    name: str
    model: Path
    server: Path
    llama_cpp: str


@dataclass
class Server:
    pack: Pack
    url: str
    api_key: str
    process: subprocess.Popen
    started: float


_lock = threading.Lock()
_server: Server | None = None
_error: str | None = None


def default_locations() -> list[Path]:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return [Path(base) / "Programs" / "HanJangJeju-AI"] if base else []
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "HanJangJeju" / "ai-pack"]
    return [Path.home() / ".local" / "share" / "HanJangJeju" / "ai-pack"]


def _inside(root: Path, rel: str) -> Path:
    try:
        path = (root / rel).resolve()
        base = root.resolve()
    except OSError as err:
        raise PackError(f"AI 팩 파일 경로를 확인하지 못했어요: {rel}") from err
    if base not in path.parents:
        raise PackError(f"AI 팩 파일 경로가 팩 폴더 밖을 가리켜요: {rel}")
    return path


def load(root: Path) -> Pack:
    """팩 폴더를 검사한다. 모델 해시는 팩을 만들 때 확인하므로 여기서는 크기만 본다(1GB 해시는 느리다)."""
    try:
        meta = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise PackError(f"AI 팩 설명 파일을 읽지 못했어요: {err}") from err
    if not isinstance(meta, dict):
        raise PackError("AI 팩 설명 파일이 잘못됐어요: 객체가 아니에요")
    if meta.get("format") != FORMAT:
        raise PackError(f"이 프로그램이 모르는 AI 팩 형식이에요: {meta.get('format')}")
    try:
        model = _inside(root, str(meta["model"]))
        server = _inside(root, str(meta["server"]))
        size = int(meta["model_size"])
    except (KeyError, TypeError, ValueError) as err:
        raise PackError(f"AI 팩 설명 파일이 잘못됐어요: {err}") from err
    try:
        server_ok = server.is_file()
        model_ok = model.is_file() and model.stat().st_size == size
    except OSError as err:
        raise PackError(f"AI 팩 파일을 확인하지 못했어요: {err}") from err
    if not server_ok:
        raise PackError("AI 팩의 서버 파일이 없어요. AI 팩을 다시 설치해 주세요.")
    if not model_ok:
        raise PackError("AI 팩의 모델 파일이 없거나 손상됐어요. AI 팩을 다시 설치해 주세요.")
    return Pack(root=root, name=str(meta.get("name") or model.stem), model=model, server=server, llama_cpp=str(meta.get("llama_cpp", "")))


def find() -> Pack | None:
    """팩을 찾는다. 없으면 None, 있는데 잘못됐으면 PackError."""
    configured = os.environ.get("JEJU_AI_PACK", "").strip()
    if configured.lower() == "off":
        return None
    if configured:
        root = Path(configured)
        if not (root / MANIFEST).exists():
            # 지정한 경로를 잘못 적었으면 조용히 넘어가지 않는다
            raise PackError(f"JEJU_AI_PACK으로 지정한 곳에 AI 팩이 없어요: {root}")
        return load(root)
    for root in default_locations():
        if (root / MANIFEST).exists():
            return load(root)
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _log_path() -> Path:
    from . import privacy

    path = privacy.settings_path().parent / "ai-server.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def start() -> Server | None:
    """팩이 있으면 서버를 켠다. 이미 켜져 있으면 그대로 둔다. 팩이 없거나 켜지 못하면 None.

    어떤 실패도 예외로 내보내지 않는다. 엔진은 AI 없이도 켜져야 한다(M03). 이유는 error()로 알린다.
    """
    global _server, _error
    with _lock:
        if _server and _server.process.poll() is None:
            return _server
        _server, _error = None, None
        try:
            pack = find()
            if pack is None:
                return None
            for attempt in range(START_ATTEMPTS):
                server = _spawn(pack)
                try:
                    server.process.wait(timeout=EARLY_EXIT_SECONDS)
                except subprocess.TimeoutExpired:
                    _server = server  # 바로 끝나지 않았다. 모델을 불러오는 중이다.
                    return _server
                _error = f"AI 팩 서버가 바로 멈췄어요(종료 코드 {server.process.returncode}). 기록: {_log_path()}"
            return None
        except Exception as err:  # noqa: BLE001 - 엔진 시작을 막지 않는다
            _error = f"AI 팩 서버를 켜지 못했어요: {err}"
            return None


def _spawn(pack: Pack) -> Server:
    port = _free_port()
    key = secrets.token_urlsafe(32)
    env = {**os.environ, "LLAMA_API_KEY": key}
    args = [
        str(pack.server), "-m", str(pack.model),
        "--host", "127.0.0.1", "--port", str(port),
        "-c", "4096", "-np", "1", "-ngl", "0",
        "--no-webui", "--no-slots", "--reasoning", "off",
        # 기본 상세도(3)는 처리 시간만 남기고 질문 문장은 남기지 않는다. 바뀌지 않게 명시한다.
        "--log-verbosity", "3",
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with _log_path().open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            args, cwd=pack.server.parent, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
        )
    if os.name == "nt":
        # Popen과 Job 연결 사이의 아주 짧은 틈에 엔진이 강제 종료되면 서버가 남을 수 있다(남은 위험으로 기록).
        _windows_job.attach(process)
    return Server(pack=pack, url=f"http://127.0.0.1:{port}", api_key=key, process=process, started=time.monotonic())


def current() -> Server | None:
    return _server


def error() -> str | None:
    return _error


def health() -> tuple[bool, str]:
    """(준비됨, 사유). 서버가 모델을 다 불러오면 /health가 200이다(불러오는 중에는 503)."""
    server = _server
    if server is None:
        return False, _error or "AI 팩이 없어요."
    code = server.process.poll()
    if code is not None:
        return False, f"AI 팩 서버가 멈췄어요(종료 코드 {code}). 기록: {_log_path()}"
    try:
        with _OPENER.open(f"{server.url}/health", timeout=2) as res:
            return res.status == 200, ""
    except urllib.error.HTTPError as err:
        if err.code == 503:
            return False, "AI 팩 모델을 불러오는 중이에요."
        return False, f"AI 팩 서버 응답이 이상해요({err.code})."
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False, "AI 팩 서버를 켜는 중이에요."


def stop() -> None:
    global _server
    with _lock:
        server, _server = _server, None
    if server and server.process.poll() is None:
        server.process.terminate()
        try:
            server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.process.kill()


atexit.register(stop)


class _WindowsJob:
    """엔진 프로세스가 끝나면(강제 종료 포함) 묶인 서버도 끝나게 하는 Job Object.

    창 프로그램이 엔진을 이미 Job에 넣었어도 Windows 8부터 중첩 Job이 되므로 그대로 동작한다.
    `--open`(브라우저 바로가기)처럼 바깥 Job이 없을 때도 서버가 남지 않는다.
    """

    def __init__(self) -> None:
        self._handle = None

    def _create(self):
        import ctypes
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject")
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        return kernel32, handle

    def attach(self, process: subprocess.Popen) -> None:
        try:
            if self._handle is None:
                self._kernel32, self._handle = self._create()  # 핸들은 엔진이 끝날 때 OS가 닫는다
            if not self._kernel32.AssignProcessToJobObject(self._handle, int(process._handle)):  # type: ignore[attr-defined]
                import ctypes

                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
        except OSError as err:
            # 묶지 못해도 정상 종료 때는 stop()이 끈다. 원인은 엔진 기록에 남긴다.
            print(f"AI 팩 서버를 Job Object에 묶지 못했어요: {err}", file=sys.stderr, flush=True)


_windows_job = _WindowsJob()
