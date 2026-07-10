from __future__ import annotations

import json
import time
from typing import Protocol

import httpx

from mewcode.integrations.feishu.config import FeishuSettings


class FeishuApiError(RuntimeError):
    pass


class FeishuReplyClient(Protocol):
    async def reply_text(self, message_id: str, text: str) -> None: ...


class FeishuClient:
    def __init__(
        self,
        settings: FeishuSettings,
        base_url: str = "https://open.feishu.cn",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = base_url.rstrip("/")
        self._http = http_client or httpx.AsyncClient(timeout=30)
        self._owns_client = http_client is None
        self._tenant_access_token = ""
        self._tenant_access_token_expires_at = 0.0

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def _get_tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._tenant_access_token_expires_at:
            return self._tenant_access_token

        response = await self._http.post(
            f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self._settings.app_id,
                "app_secret": self._settings.app_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise FeishuApiError(f"Failed to get tenant_access_token: {data}")

        token = data.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuApiError("tenant_access_token response missing token")

        expire = int(data.get("expire", 7200))
        self._tenant_access_token = token
        self._tenant_access_token_expires_at = now + max(expire - 120, 60)
        return token

    async def reply_text(self, message_id: str, text: str) -> None:
        token = await self._get_tenant_access_token()
        response = await self._http.post(
            f"{self._base_url}/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise FeishuApiError(f"Failed to reply message: {data}")

