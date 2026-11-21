"""로컬 모델(Ollama) 연결. 127.0.0.1과 localhost만 허용한다 (설계 7절).

원본 행은 이 모듈로 보내지 않는다. 호출하는 쪽이 열 정의와 분류 값 예시만 넘긴다.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = os.environ.get("JEJU_MODEL", "qwen3:1.7b")  # 평가: docs/model-eval.md
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ModelUnavailable(RuntimeError):
    pass


def base_url() -> str:
    """이름만 보지 않고 실제로 해석한 IP가 모두 loopback일 때만 쓴다."""
    url = os.environ.get("JEJU_OLLAMA_URL", DEFAULT_URL).rstrip("/")
    host = urlparse(url).hostname or ""
    if host not in LOOPBACK:
        raise ModelUnavailable(f"모델 주소는 이 PC(127.0.0.1)만 쓸 수 있어요: {url}")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as err:
        raise ModelUnavailable(f"모델 주소를 찾지 못했어요: {url}") from err
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_loopback for a in addresses):
        raise ModelUnavailable(f"모델 주소가 이 PC 밖을 가리켜요: {url}")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # 리다이렉트를 따르지 않는다
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _request(path: str, payload: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{base_url()}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
    )
    try:
        with _OPENER.open(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise ModelUnavailable(f"로컬 모델에 연결하지 못했어요: {err}") from err


def status(model: str = DEFAULT_MODEL) -> dict:
    try:
        tags = _request("/api/tags", timeout=2)
    except ModelUnavailable as err:
        return {"available": False, "model": model, "reason": str(err)}
    names = {m.get("name") for m in tags.get("models", [])}
    if model not in names:
        return {"available": False, "model": model, "reason": f"모델 {model}이 설치되어 있지 않아요. 'ollama pull {model}'로 받아 주세요."}
    return {"available": True, "model": model}


@dataclass
class ChatResult:
    content: str
    latency_ms: int
    eval_count: int
    prompt_tokens: int


def chat_json(system: str, messages: list[dict], schema: dict, model: str = DEFAULT_MODEL, timeout: float = 20) -> ChatResult:
    """구조화 출력으로 JSON 하나를 받는다. 온도 0, 출력 길이 상한(기획안 13.3)."""
    started = time.monotonic()
    body = _request(
        "/api/chat",
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 300, "num_ctx": 4096},
            "keep_alive": "30m",
            # Qwen3 같은 생각 모드 모델은 계획만 필요하므로 생각을 끈다.
            **({"think": False} if model.startswith("qwen3") else {}),
        },
        timeout=timeout,
    )
    return ChatResult(
        content=body.get("message", {}).get("content", ""),
        latency_ms=int((time.monotonic() - started) * 1000),
        eval_count=int(body.get("eval_count", 0)),
        prompt_tokens=int(body.get("prompt_eval_count", 0)),
    )
