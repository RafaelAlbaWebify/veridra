from __future__ import annotations

import json
from dataclasses import dataclass
from typing import IO, Any

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 256_000


class BrowserProtocolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProtocolRequest:
    request_id: str
    command: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProtocolResponse:
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


def _decode_message(line: str) -> dict[str, Any]:
    if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise BrowserProtocolError("Browser protocol message exceeded the size limit.")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise BrowserProtocolError("Browser protocol returned malformed JSON.") from exc
    if not isinstance(value, dict):
        raise BrowserProtocolError("Browser protocol message must be a JSON object.")
    if value.get("protocol_version") != PROTOCOL_VERSION:
        raise BrowserProtocolError("Browser protocol version mismatch.")
    return value


def encode_request(request: ProtocolRequest) -> str:
    return json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request.request_id,
            "command": request.command,
            "payload": request.payload,
        },
        separators=(",", ":"),
    ) + "\n"


def decode_request(line: str) -> ProtocolRequest:
    value = _decode_message(line)
    request_id = value.get("request_id")
    command = value.get("command")
    payload = value.get("payload", {})
    if not isinstance(request_id, str) or not request_id:
        raise BrowserProtocolError("Browser protocol request_id is missing.")
    if not isinstance(command, str) or not command:
        raise BrowserProtocolError("Browser protocol command is missing.")
    if not isinstance(payload, dict):
        raise BrowserProtocolError("Browser protocol payload must be an object.")
    return ProtocolRequest(request_id=request_id, command=command, payload=payload)


def encode_response(response: ProtocolResponse) -> str:
    value: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": response.request_id,
        "ok": response.ok,
    }
    if response.ok:
        value["result"] = response.result or {}
    else:
        value["error"] = {
            "code": response.error_code or "browser_error",
            "message": response.error_message or "The browser command failed.",
        }
    return json.dumps(value, separators=(",", ":")) + "\n"


def decode_response(line: str, *, expected_request_id: str) -> ProtocolResponse:
    value = _decode_message(line)
    request_id = value.get("request_id")
    if request_id != expected_request_id:
        raise BrowserProtocolError("Browser protocol response request_id mismatch.")
    ok = value.get("ok")
    if not isinstance(ok, bool):
        raise BrowserProtocolError("Browser protocol response is missing ok state.")
    if ok:
        result = value.get("result", {})
        if not isinstance(result, dict):
            raise BrowserProtocolError("Browser protocol result must be an object.")
        return ProtocolResponse(request_id=request_id, ok=True, result=result)
    error = value.get("error")
    if not isinstance(error, dict):
        raise BrowserProtocolError("Browser protocol error envelope is missing.")
    code = error.get("code")
    message = error.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        raise BrowserProtocolError("Browser protocol error envelope is invalid.")
    return ProtocolResponse(
        request_id=request_id,
        ok=False,
        error_code=code,
        error_message=message,
    )


def write_message(stream: IO[str], message: str) -> None:
    if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise BrowserProtocolError("Browser protocol message exceeded the size limit.")
    stream.write(message)
    stream.flush()
