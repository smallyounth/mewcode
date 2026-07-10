from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from mewcode.integrations.feishu.app import create_app
from mewcode.integrations.feishu.config import FeishuConfigError, FeishuSettings


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mewcode-feishu",
        description="Run the MewCode Feishu bot webhook service",
    )
    parser.add_argument("--host", default=None, help="Host to bind, defaults to FEISHU_HOST")
    parser.add_argument("--port", type=int, default=None, help="Port to bind, defaults to FEISHU_PORT")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        settings = FeishuSettings.from_env()
    except FeishuConfigError as exc:
        print(f"Feishu config error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = create_app(settings=settings)
    uvicorn.run(
        app,
        host=args.host or settings.host,
        port=args.port or settings.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

