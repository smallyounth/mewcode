from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from mewcode.integrations.feishu.config import FeishuSettings


class FeishuEventError(ValueError):
    pass


@dataclass(frozen=True)
class FeishuChallenge:
    challenge: str


@dataclass(frozen=True)
class FeishuMessage:
    event_id: str
    message_id: str
    chat_id: str
    sender_open_id: str
    text: str


def make_lark_signature(
    timestamp: str,
    nonce: str,
    signing_key: str,
    body: bytes,
) -> str:
    raw = timestamp.encode() + nonce.encode() + signing_key.encode() + body
    digest = hashlib.sha256(raw).digest()
    return base64.b64encode(digest).decode()


def verify_lark_signature(
    headers: Mapping[str, str],
    signing_key: str,
    body: bytes,
) -> bool:
    if not signing_key:
        return True

    normalized = {key.lower(): value for key, value in headers.items()}
    timestamp = normalized.get("x-lark-request-timestamp", "")
    nonce = normalized.get("x-lark-request-nonce", "")
    signature = normalized.get("x-lark-signature", "")
    if not timestamp or not nonce or not signature:
        return False

    expected = make_lark_signature(timestamp, nonce, signing_key, body)
    return hmac.compare_digest(expected, signature)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise FeishuEventError("Encrypted event payload is empty")
    pad = data[-1]
    if pad < 1 or pad > 16:
        raise FeishuEventError("Invalid encrypted event padding")
    if data[-pad:] != bytes([pad]) * pad:
        raise FeishuEventError("Invalid encrypted event padding")
    return data[:-pad]


def decrypt_event_payload(encrypted: str, encrypt_key: str) -> dict[str, Any]:
    if not encrypt_key:
        raise FeishuEventError("Encrypted event received but FEISHU_ENCRYPT_KEY is empty")

    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = key[:16]
    try:
        ciphertext = base64.b64decode(encrypted)
    except ValueError as exc:
        raise FeishuEventError("Encrypted event payload is not valid base64") from exc

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    plaintext = _pkcs7_unpad(padded)
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuEventError("Encrypted event payload is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise FeishuEventError("Encrypted event payload must decode to an object")
    return decoded


def decode_event_body(body: bytes, settings: FeishuSettings) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuEventError("Event body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise FeishuEventError("Event body must be a JSON object")
    encrypted = payload.get("encrypt")
    if isinstance(encrypted, str) and encrypted:
        return decrypt_event_payload(encrypted, settings.encrypt_key)
    return payload


def _verify_token(payload: Mapping[str, Any], settings: FeishuSettings) -> None:
    tokens = [
        payload.get("token"),
        payload.get("header", {}).get("token") if isinstance(payload.get("header"), dict) else None,
    ]
    if settings.verification_token not in tokens:
        raise FeishuEventError("Feishu verification token mismatch")


def _parse_text_content(raw: Any) -> str:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw
    elif isinstance(raw, dict):
        data = raw
    else:
        return ""
    text = data.get("text", "")
    return text if isinstance(text, str) else ""


def parse_event(payload: dict[str, Any], settings: FeishuSettings) -> FeishuChallenge | FeishuMessage | None:
    if payload.get("type") == "url_verification" and isinstance(payload.get("challenge"), str):
        _verify_token(payload, settings)
        return FeishuChallenge(challenge=payload["challenge"])

    header = payload.get("header")
    if not isinstance(header, dict):
        return None

    _verify_token(payload, settings)

    event_type = header.get("event_type")
    event = payload.get("event")
    if (
        event_type == "url_verification"
        and isinstance(event, dict)
        and isinstance(event.get("challenge"), str)
    ):
        return FeishuChallenge(challenge=event["challenge"])

    if event_type != "im.message.receive_v1":
        return None

    if not isinstance(event, dict):
        return None

    message = event.get("message")
    sender = event.get("sender")
    if not isinstance(message, dict) or not isinstance(sender, dict):
        return None

    if message.get("message_type") != "text":
        return None

    sender_id = sender.get("sender_id")
    if not isinstance(sender_id, dict):
        return None

    text = _parse_text_content(message.get("content"))
    if not text.strip():
        return None

    return FeishuMessage(
        event_id=str(header.get("event_id", "")),
        message_id=str(message.get("message_id", "")),
        chat_id=str(message.get("chat_id", "")),
        sender_open_id=str(sender_id.get("open_id", "")),
        text=text.strip(),
    )
