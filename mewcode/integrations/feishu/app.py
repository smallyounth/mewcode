from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Protocol

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from mewcode.integrations.feishu.client import FeishuClient, FeishuReplyClient
from mewcode.integrations.feishu.config import FeishuConfigError, FeishuSettings
from mewcode.integrations.feishu.events import (
    FeishuChallenge,
    FeishuEventError,
    FeishuMessage,
    decode_event_body,
    parse_event,
    verify_lark_signature,
)
from mewcode.integrations.feishu.runner import MewcodeTaskRunner, TaskResult

log = logging.getLogger(__name__)


class TaskRunner(Protocol):
    async def run(self, prompt: str) -> TaskResult: ...


@dataclass
class FeishuBotService:
    settings: FeishuSettings
    runner: TaskRunner
    reply_client: FeishuReplyClient

    async def handle_request(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
        background_tasks: BackgroundTasks,
    ) -> JSONResponse:
        if not verify_lark_signature(headers, self.settings.event_signing_key, raw_body):
            return JSONResponse({"code": 401, "msg": "invalid signature"}, status_code=401)

        try:
            payload = decode_event_body(raw_body, self.settings)
            event = parse_event(payload, self.settings)
        except FeishuEventError as exc:
            return JSONResponse({"code": 400, "msg": str(exc)}, status_code=400)

        if isinstance(event, FeishuChallenge):
            return JSONResponse({"challenge": event.challenge})

        if isinstance(event, FeishuMessage):
            if not self._is_allowed(event.sender_open_id):
                if event.message_id:
                    background_tasks.add_task(
                        self.reply_client.reply_text,
                        event.message_id,
                        "未授权：这个机器人当前只允许指定用户使用。",
                    )
                return JSONResponse({"code": 0, "msg": "ignored unauthorized sender"})

            background_tasks.add_task(self._execute_and_reply, event)
            return JSONResponse({"code": 0, "msg": "ok"})

        return JSONResponse({"code": 0, "msg": "ignored"})

    def _is_allowed(self, open_id: str) -> bool:
        return bool(open_id) and (
            not self.settings.allowed_open_ids
            or open_id in self.settings.allowed_open_ids
        )

    async def _execute_and_reply(self, message: FeishuMessage) -> None:
        try:
            if self.settings.ack_text:
                await self.reply_client.reply_text(message.message_id, self.settings.ack_text)

            result = await self.runner.run(message.text)
            await self.reply_client.reply_text(
                message.message_id,
                format_task_result(result, self.settings.reply_max_chars),
            )
        except Exception as exc:
            log.exception("Failed to execute Feishu task")
            with_error = f"执行失败：{exc}"
            try:
                await self.reply_client.reply_text(message.message_id, with_error)
            except Exception:
                log.exception("Failed to send Feishu error reply")


def format_task_result(result: TaskResult, max_chars: int) -> str:
    if result.error:
        text = f"执行失败：{result.error}"
    else:
        parts = [result.text.strip() or "任务已完成。"]
        if result.tool_uses:
            tools = ", ".join(result.tool_uses[:8])
            if len(result.tool_uses) > 8:
                tools += f" 等 {len(result.tool_uses)} 次工具调用"
            parts.append(f"\n\n工具：{tools}")
        if result.input_tokens or result.output_tokens:
            parts.append(
                f"\n\nToken：input {result.input_tokens}, output {result.output_tokens}"
            )
        text = "".join(parts)

    if len(text) <= max_chars:
        return text
    suffix = "\n\n[输出过长，已截断]"
    return text[: max_chars - len(suffix)] + suffix


def create_app(
    settings: FeishuSettings | None = None,
    runner: TaskRunner | None = None,
    reply_client: FeishuReplyClient | None = None,
) -> FastAPI:
    try:
        resolved_settings = settings or FeishuSettings.from_env()
    except FeishuConfigError:
        raise

    resolved_runner = runner or MewcodeTaskRunner(resolved_settings)
    resolved_reply_client = reply_client or FeishuClient(resolved_settings)
    service = FeishuBotService(
        settings=resolved_settings,
        runner=resolved_runner,
        reply_client=resolved_reply_client,
    )

    app = FastAPI(title="MewCode Feishu Bot")
    app.state.feishu_service = service

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/feishu/events")
    async def feishu_events(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
        raw_body = await request.body()
        return await service.handle_request(raw_body, request.headers, background_tasks)

    return app

