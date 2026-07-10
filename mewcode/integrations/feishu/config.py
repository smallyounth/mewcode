from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class FeishuConfigError(ValueError):
    pass


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise FeishuConfigError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class FeishuSettings:
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str = ""
    event_signing_key: str = ""
    allowed_open_ids: tuple[str, ...] = ()
    work_dir: str = "."
    config_path: str = ""
    permission_mode: str = "dontAsk"
    host: str = "127.0.0.1"
    port: int = 8787
    ack_text: str = "已收到，正在执行。"
    reply_max_chars: int = 3500
    max_iterations: int = 20

    @classmethod
    def from_env(cls) -> FeishuSettings:
        settings = cls(
            app_id=os.environ.get("FEISHU_APP_ID", ""),
            app_secret=os.environ.get("FEISHU_APP_SECRET", ""),
            verification_token=os.environ.get("FEISHU_VERIFICATION_TOKEN", ""),
            encrypt_key=os.environ.get("FEISHU_ENCRYPT_KEY", ""),
            event_signing_key=(
                os.environ.get("FEISHU_EVENT_SIGNING_KEY", "")
                or os.environ.get("FEISHU_ENCRYPT_KEY", "")
            ),
            allowed_open_ids=_split_csv(os.environ.get("FEISHU_ALLOWED_OPEN_IDS", "")),
            work_dir=os.environ.get("FEISHU_WORK_DIR", "."),
            config_path=os.environ.get("FEISHU_MEWCODE_CONFIG", ""),
            permission_mode=os.environ.get("FEISHU_PERMISSION_MODE", "dontAsk"),
            host=os.environ.get("FEISHU_HOST", "127.0.0.1"),
            port=_int_from_env("FEISHU_PORT", 8787),
            ack_text=os.environ.get("FEISHU_ACK_TEXT", "已收到，正在执行。"),
            reply_max_chars=_int_from_env("FEISHU_REPLY_MAX_CHARS", 3500),
            max_iterations=_int_from_env("FEISHU_MAX_ITERATIONS", 20),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("FEISHU_APP_ID", self.app_id),
                ("FEISHU_APP_SECRET", self.app_secret),
                ("FEISHU_VERIFICATION_TOKEN", self.verification_token),
            )
            if not value
        ]
        if missing:
            raise FeishuConfigError("Missing required env vars: " + ", ".join(missing))

        if self.reply_max_chars < 100:
            raise FeishuConfigError("FEISHU_REPLY_MAX_CHARS must be at least 100")
        if self.max_iterations < 1:
            raise FeishuConfigError("FEISHU_MAX_ITERATIONS must be at least 1")

    @property
    def work_path(self) -> Path:
        return Path(self.work_dir).expanduser().resolve()

    @property
    def mewcode_config_path(self) -> Path | None:
        if not self.config_path:
            return None
        return Path(self.config_path).expanduser().resolve()

