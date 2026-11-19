"""Cloudflare Workers AI 계획 전용 연결. 오류에 비밀값/응답 원문을 싣지 않는다."""
from __future__ import annotations

import json
import os
import re

import httpx

DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
FREE_MODELS = {DEFAULT_MODEL}
transport = None  # 단위 테스트의 HTTP 경계 주입점


class ModelError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def status() -> dict:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    model = os.getenv("CLOUDFLARE_MODEL", DEFAULT_MODEL)
    reason = ""
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account) or not token:
        reason = "model_unconfigured"
    elif os.getenv("CLOUDFLARE_FREE_PLAN_CONFIRMED") != "1":
        reason = "free_plan_unconfirmed"
    elif model not in FREE_MODELS:
        reason = "model_not_allowed"
    return {"available": not reason, "ready": not reason, "model": model, "provider": "cloudflare", "reason": reason}


def chat_json(system: str, messages: list[dict], schema: dict) -> dict:
    state = status()
    if not state["available"]:
        raise ModelError(state["reason"])
    url = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/ai/run/{state['model']}"
    try:
        with httpx.Client(timeout=20, transport=transport, follow_redirects=False) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"}, json={"messages": [{"role": "system", "content": system}, *messages], "max_tokens": 300, "temperature": 0, "stream": False, "response_format": {"type": "json_schema", "json_schema": schema}})
    except httpx.TimeoutException:
        raise ModelError("timeout") from None
    except httpx.HTTPError:
        raise ModelError("model_unavailable") from None
    try:
        payload = response.json()
    except ValueError:
        raise ModelError("model_unavailable") from None
    if response.status_code != 200 or payload.get("success") is False:
        errors = str(payload.get("errors", "")).lower()
        code = "quota_exhausted" if any(word in errors for word in ("quota", "daily", "neuron limit")) else "rate_limited" if response.status_code == 429 else "model_unavailable"
        raise ModelError(code)
    content = payload.get("result", {}).get("response")
    try:
        result = json.loads(content) if isinstance(content, str) and len(content) <= 16000 else content
        if not isinstance(result, dict):
            raise ValueError
        return result
    except ValueError:
        raise ModelError("parse_failed") from None
