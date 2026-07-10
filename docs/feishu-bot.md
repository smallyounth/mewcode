# Feishu Bot Integration

This integration runs MewCode behind a Feishu bot webhook. It is intended for a
personal bot first: one allowed Feishu user, one fixed workspace, and a private
server-side environment.

## What Is Included

- `mewcode-feishu` command for a local FastAPI webhook service
- `POST /feishu/events` for Feishu event callbacks
- `GET /health` for local health checks
- URL verification challenge handling
- `im.message.receive_v1` text message handling
- Optional encrypted event payload decoding
- Optional request signature verification
- Feishu message replies through the reply-message API
- A personal `open_id` allowlist
- Background execution so Feishu callbacks return quickly

## Local Setup

Install the project in editable mode:

```bash
python -m pip install -e .
```

Create or reuse your MewCode provider config:

```bash
mewcode --setup
```

Copy the example environment file and fill in your values:

```bash
cp examples/feishu.env.example .env.feishu
```

PowerShell users can set values in the current shell instead:

```powershell
$env:FEISHU_APP_ID="cli_xxx"
$env:FEISHU_APP_SECRET="..."
$env:FEISHU_VERIFICATION_TOKEN="..."
$env:FEISHU_ALLOWED_OPEN_IDS="ou_xxx"
$env:FEISHU_WORK_DIR="D:\workspaces\mewcode-bot"
$env:FEISHU_MEWCODE_CONFIG="D:\夸克Files\mewcode-python\.mewcode\config.yaml"
$env:FEISHU_PERMISSION_MODE="dontAsk"
```

Start the service:

```bash
mewcode-feishu --host 127.0.0.1 --port 8787
```

If your local editable environment does not expose console scripts correctly,
use the module entrypoint:

```bash
python -m mewcode.integrations.feishu --host 127.0.0.1 --port 8787
```

Check health:

```bash
curl http://127.0.0.1:8787/health
```

## Feishu App Configuration

In Feishu Open Platform:

1. Create an internal app.
2. Enable bot capability.
3. Add event subscription with request URL:

   ```text
   https://your-domain.example/feishu/events
   ```

4. Subscribe to:

   ```text
   im.message.receive_v1
   ```

5. Grant message permissions required for receiving and replying to bot messages.
6. Install or publish the app to your tenant.

For local testing before you buy a server, expose your local port with a trusted
HTTPS tunnel, then use that tunnel URL as the Feishu event callback URL.

## Finding Your open_id

Temporarily leave `FEISHU_ALLOWED_OPEN_IDS` empty in a private test environment,
send a message to the bot, and inspect the service logs or add a breakpoint in
`mewcode.integrations.feishu.events.parse_event`. Then set:

```bash
FEISHU_ALLOWED_OPEN_IDS=ou_your_open_id
```

Do not run a command-executing bot without an allowlist on a public callback URL.

## Security Defaults

The first version is deliberately narrow:

- one fixed workspace via `FEISHU_WORK_DIR`
- optional encrypted payload support via `FEISHU_ENCRYPT_KEY`
- optional signature verification via `FEISHU_EVENT_SIGNING_KEY`
- command/file execution is constrained by MewCode's permission checker and path sandbox
- dangerous commands are still blocked by the existing detector

`FEISHU_PERMISSION_MODE=dontAsk` allows the non-interactive bot to execute file
edits and commands without a TUI approval dialog. Keep this limited to your own
open_id and your own server.

## Server Deployment Later

After buying the server, use this shape:

```text
Nginx/Caddy HTTPS :443
  -> 127.0.0.1:8787
  -> mewcode-feishu managed by systemd
```

Recommended server layout:

```text
/srv/mewcode/app        # this repository
/srv/mewcode/workspace  # fixed bot workspace
/etc/mewcode/feishu.env # environment file, not committed
```
