from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi.testclient import TestClient

from mewcode.integrations.feishu.app import create_app, format_task_result
from mewcode.integrations.feishu.config import FeishuSettings
from mewcode.integrations.feishu.events import (
    FeishuChallenge,
    FeishuMessage,
    decode_event_body,
    make_lark_signature,
    parse_event,
    verify_lark_signature,
)
from mewcode.integrations.feishu.runner import TaskResult


def _settings(**overrides) -> FeishuSettings:
    values = {
        "app_id": "cli_xxx",
        "app_secret": "secret",
        "verification_token": "verify-token",
        "allowed_open_ids": ("ou_me",),
        "event_signing_key": "",
    }
    values.update(overrides)
    return FeishuSettings(**values)


def _message_payload(text: str = "hello") -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": "event-1",
            "event_type": "im.message.receive_v1",
            "token": "verify-token",
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": "ou_me",
                }
            },
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def _encrypt_payload(payload: dict, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = key[:16]
    raw = json.dumps(payload, ensure_ascii=False).encode()
    pad = 16 - len(raw) % 16
    padded = raw + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode()


def test_parse_url_verification() -> None:
    event = parse_event(
        {
            "type": "url_verification",
            "token": "verify-token",
            "challenge": "challenge-value",
        },
        _settings(),
    )
    assert isinstance(event, FeishuChallenge)
    assert event.challenge == "challenge-value"


def test_parse_v2_url_verification() -> None:
    event = parse_event(
        {
            "schema": "2.0",
            "header": {
                "event_type": "url_verification",
                "token": "verify-token",
            },
            "event": {
                "challenge": "v2-challenge",
            },
        },
        _settings(),
    )
    assert isinstance(event, FeishuChallenge)
    assert event.challenge == "v2-challenge"


def test_parse_text_message_event() -> None:
    event = parse_event(_message_payload("帮我看一下项目"), _settings())
    assert isinstance(event, FeishuMessage)
    assert event.event_id == "event-1"
    assert event.message_id == "om_1"
    assert event.sender_open_id == "ou_me"
    assert event.text == "帮我看一下项目"


def test_signature_verification() -> None:
    body = b'{"hello":"world"}'
    signature = make_lark_signature("1", "nonce", "signing-key", body)
    headers = {
        "X-Lark-Request-Timestamp": "1",
        "X-Lark-Request-Nonce": "nonce",
        "X-Lark-Signature": signature,
    }
    assert verify_lark_signature(headers, "signing-key", body) is True
    assert verify_lark_signature(headers, "wrong-key", body) is False


def test_decode_encrypted_event_body() -> None:
    settings = _settings(encrypt_key="encrypt-key")
    encrypted = _encrypt_payload(_message_payload("加密消息"), "encrypt-key")
    decoded = decode_event_body(
        json.dumps({"encrypt": encrypted}).encode(),
        settings,
    )
    event = parse_event(decoded, settings)
    assert isinstance(event, FeishuMessage)
    assert event.text == "加密消息"


class FakeRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def run(self, prompt: str) -> TaskResult:
        self.prompts.append(prompt)
        return TaskResult(
            text=f"done: {prompt}",
            tool_uses=["ReadFile", "Bash"],
            input_tokens=10,
            output_tokens=20,
        )


class FakeReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    async def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


def test_app_handles_message_and_replies() -> None:
    runner = FakeRunner()
    replies = FakeReplyClient()
    app = create_app(settings=_settings(), runner=runner, reply_client=replies)

    response = TestClient(app).post("/feishu/events", json=_message_payload("执行测试"))

    assert response.status_code == 200
    assert runner.prompts == ["执行测试"]
    assert replies.replies[0] == ("om_1", "已收到，正在执行。")
    assert replies.replies[1][0] == "om_1"
    assert "done: 执行测试" in replies.replies[1][1]
    assert "ReadFile, Bash" in replies.replies[1][1]


def test_app_blocks_unauthorized_sender() -> None:
    runner = FakeRunner()
    replies = FakeReplyClient()
    payload = _message_payload("不该执行")
    payload["event"]["sender"]["sender_id"]["open_id"] = "ou_other"
    app = create_app(settings=_settings(), runner=runner, reply_client=replies)

    response = TestClient(app).post("/feishu/events", json=payload)

    assert response.status_code == 200
    assert runner.prompts == []
    assert replies.replies == [("om_1", "未授权：这个机器人当前只允许指定用户使用。")]


def test_format_task_result_truncates() -> None:
    result = TaskResult(text="x" * 200)
    formatted = format_task_result(result, max_chars=80)
    assert len(formatted) == 80
    assert formatted.endswith("[输出过长，已截断]")
