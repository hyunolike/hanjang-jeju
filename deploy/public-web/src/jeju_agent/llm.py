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


# 로컬 모델만 부르므로 프록시를 쓰지 않는다. 기본 opener는 HTTP_PROXY와 Windows 레지스트리 프록시를 따라
# 127.0.0.1 요청과 키, 질문을 기관 프록시로 보낼 수 있다.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


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
    """AI 팩 서버가 켜져 있으면 그것을, 아니면 Ollama를 본다(명세 M03)."""
    from . import aipack

    server = aipack.current()
    if server is not None:
        ready, reason = aipack.health()
        out = {"available": ready, "model": server.pack.name, "backend": "pack"}
        # 서버가 살아 있으면 모델을 불러오는 중이다. 화면은 "없음"이 아니라 "준비 중"으로 보여 준다(M07).
        return out if ready else {**out, "reason": reason, "loading": server.process.poll() is None}
    out = _ollama_status(model)
    if not out["available"]:
        out["install_hint"] = aipack.install_hint()
    if not out["available"] and aipack.error():
        out["reason"] = aipack.error()  # 팩이 있는데 잘못된 경우가 Ollama 안내보다 중요하다
        out["pack_error"] = True
    return out


def _ollama_status(model: str) -> dict:
    try:
        tags = _request("/api/tags", timeout=2)
    except ModelUnavailable as err:
        return {"available": False, "model": model, "backend": "ollama", "reason": str(err)}
    names = {m.get("name") for m in tags.get("models", [])}
    if model not in names:
        return {"available": False, "model": model, "backend": "ollama", "reason": f"모델 {model}이 설치되어 있지 않아요. 'ollama pull {model}'로 받아 주세요."}
    return {"available": True, "model": model, "backend": "ollama"}


@dataclass
class ChatResult:
    content: str
    latency_ms: int
    eval_count: int
    prompt_tokens: int


def chat_json(system: str, messages: list[dict], schema: dict, model: str = DEFAULT_MODEL, timeout: float = 20) -> ChatResult:
    """구조화 출력으로 JSON 하나를 받는다. 온도 0, 출력 길이 상한(기획안 13.3)."""
    from . import aipack

    server = aipack.current()
    if server is not None:
        return _pack_chat(server, system, messages, schema, timeout)
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


# AI 팩은 GPU 없이 CPU로 돈다. 이 Mac CPU에서 최대 9초였고 센터 PC는 더 느릴 수 있어 넉넉히 둔다(M4).
PACK_TIMEOUT = 60


def _pack_chat(server, system: str, messages: list[dict], schema: dict, timeout: float) -> ChatResult:
    """AI 팩(llama.cpp 서버)의 OpenAI 호환 API. JSON 스키마는 서버가 문법으로 강제한다.

    생각 모드는 서버를 --reasoning off로 켜서 끈다. 주소는 엔진이 만든 127.0.0.1 포트이고 키는 실행마다 새로 만든다.
    """
    timeout = max(timeout, PACK_TIMEOUT)
    started = time.monotonic()
    payload = {
        "messages": [{"role": "system", "content": system}, *messages],
        "response_format": {"type": "json_schema", "json_schema": {"name": "plan", "schema": schema}},
        "temperature": 0,
        "max_tokens": 300,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{server.url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {server.api_key}"},
        method="POST",
    )
    try:
        with _OPENER.open(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise ModelUnavailable(f"AI 팩 모델에 연결하지 못했어요: {err}") from err
    usage = body.get("usage") or {}
    choice = (body.get("choices") or [{}])[0]
    return ChatResult(
        content=(choice.get("message") or {}).get("content") or "",
        latency_ms=int((time.monotonic() - started) * 1000),
        eval_count=int(usage.get("completion_tokens", 0)),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
    )
