from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mewcode.agent import Agent
from mewcode.client import create_client, resolve_context_window
from mewcode.config import ConfigError, load_config
from mewcode.conversation import ConversationManager
from mewcode.hooks import HookConfigError, HookEngine, load_hooks
from mewcode.integrations.feishu.config import FeishuSettings
from mewcode.memory.instructions import load_instructions
from mewcode.permissions import (
    DangerousCommandDetector,
    PathSandbox,
    PermissionChecker,
    PermissionMode,
    RuleEngine,
)
from mewcode.tools import create_default_registry
from mewcode.tools.impl.tool_search import ToolSearchTool


@dataclass(frozen=True)
class TaskResult:
    text: str
    tool_uses: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class MewcodeTaskRunner:
    def __init__(self, settings: FeishuSettings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()

    async def run(self, prompt: str) -> TaskResult:
        async with self._lock:
            try:
                return await self._run_locked(prompt)
            except (ConfigError, HookConfigError, ValueError) as exc:
                return TaskResult(text="", error=str(exc))
            except Exception as exc:
                return TaskResult(text="", error=f"任务执行失败: {exc}")

    async def _run_locked(self, prompt: str) -> TaskResult:
        work_dir = self._settings.work_path
        work_dir.mkdir(parents=True, exist_ok=True)

        config_path = self._settings.mewcode_config_path
        config = load_config(config_path)
        provider = config.providers[0]
        client = create_client(provider)
        await resolve_context_window(provider)

        permission_mode = PermissionMode(self._settings.permission_mode)
        home = Path.home()
        checker = PermissionChecker(
            detector=DangerousCommandDetector(),
            sandbox=PathSandbox(str(work_dir)),
            rule_engine=RuleEngine(
                user_rules_path=home / ".mewcode" / "permissions.yaml",
                project_rules_path=work_dir / ".mewcode" / "permissions.yaml",
                local_rules_path=work_dir / ".mewcode" / "permissions.local.yaml",
            ),
            mode=permission_mode,
        )

        hooks = load_hooks(config.raw_hooks)
        hook_engine = HookEngine(hooks) if hooks else None

        registry = create_default_registry()
        registry.register(ToolSearchTool(registry, protocol=provider.protocol))

        events: dict[str, Any] = {
            "tool_uses": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }

        def on_event(event: dict[str, Any]) -> None:
            event_type = event.get("type")
            if event_type == "tool_use":
                tool_name = str(event.get("toolName", ""))
                if tool_name:
                    events["tool_uses"].append(tool_name)
            elif event_type == "usage":
                usage = event.get("usage", {})
                if isinstance(usage, dict):
                    events["input_tokens"] = int(usage.get("inputTokens", 0) or 0)
                    events["output_tokens"] = int(usage.get("outputTokens", 0) or 0)

        agent = Agent(
            client=client,
            registry=registry,
            protocol=provider.protocol,
            work_dir=str(work_dir),
            max_iterations=self._settings.max_iterations,
            permission_checker=checker,
            context_window=provider.get_context_window(),
            instructions_content=load_instructions(str(work_dir)),
            hook_engine=hook_engine,
        )
        conversation = ConversationManager()
        text = await agent.run_to_completion(prompt, conversation, event_callback=on_event)
        return TaskResult(
            text=text or "任务已完成，但模型没有返回文本。",
            tool_uses=list(events["tool_uses"]),
            input_tokens=int(events["input_tokens"]),
            output_tokens=int(events["output_tokens"]),
        )

