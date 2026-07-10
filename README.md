# MewCode

MewCode is a terminal AI coding assistant. It can run with Anthropic, OpenAI, or any OpenAI-compatible model provider.

Users own their provider configuration: API keys, model names, base URLs, token limits, and permission mode are all configured locally in `.mewcode/config.yaml`. Local config files are ignored by Git, so private keys should not be committed.

## Install

Requires Python 3.11 or newer.

```bash
git clone https://github.com/smallyounth/mewcode.git
cd mewcode
python -m pip install -e .
```

If you use `uv`:

```bash
uv sync --dev
```

## First Run

Start MewCode:

```bash
mewcode
```

If no config exists, MewCode will open a setup wizard before entering the chat UI. The wizard asks for:

- provider: DeepSeek, OpenAI, Anthropic, or custom OpenAI-compatible
- model name
- API key environment variable, or a direct API key if you choose to save it locally
- optional context window and max output tokens

You can run the setup wizard again at any time:

```bash
mewcode --setup
```

## Feishu Bot

MewCode can run behind a personal Feishu bot webhook for server-side command
execution and answers in Feishu. See [docs/feishu-bot.md](docs/feishu-bot.md).

## Manual Configure

Create a local config file:

PowerShell:

```powershell
mkdir .mewcode
copy config.example.yaml .mewcode\config.yaml
```

On macOS/Linux, use:

```bash
mkdir -p .mewcode
cp config.example.yaml .mewcode/config.yaml
```

Then edit `.mewcode/config.yaml` and choose your own provider, API key environment variable, base URL, and model.

Example for DeepSeek:

```yaml
providers:
  - name: deepseek
    protocol: openai-compat
    base_url: https://api.deepseek.com
    model: deepseek-chat
    api_key: ${DEEPSEEK_API_KEY}
    context_window: 0
    max_output_tokens: 8192

permission_mode: default
```

Set the API key in your shell.

PowerShell:

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
```

macOS/Linux:

```bash
export DEEPSEEK_API_KEY="your-api-key"
```

For persistent environment variables, configure them in your shell profile or operating system environment settings.

## Provider Protocols

Use one of these `protocol` values:

```text
anthropic       Anthropic Messages API
openai          OpenAI Responses API
openai-compat   OpenAI-compatible Chat Completions API
```

Most third-party providers should use `openai-compat`.

You can change the model by editing only the `model` field:

```yaml
model: your-provider-model-name
```

If the model context window is unknown, leave this as `0` and MewCode will use a fallback:

```yaml
context_window: 0
```

Set it explicitly if your provider has a larger or smaller context window:

```yaml
context_window: 128000
```

## Run

Interactive terminal UI:

```bash
mewcode
```

Or without installing the console script:

```bash
python -m mewcode
```

Run a single prompt and print the result:

```bash
mewcode -p "Summarize this project"
```

## Permission Modes

You can set the default permission mode in `.mewcode/config.yaml`:

```yaml
permission_mode: default
```

Or override it at runtime:

```bash
mewcode --mode plan
mewcode --mode acceptEdits
```

Available modes:

```text
default
acceptEdits
plan
bypassPermissions
custom
dontAsk
```

## Development

Run tests:

```bash
python -m pytest
```

Build the package:

```bash
uv build
```

The repository includes GitHub Actions workflows for CI and release publishing.

## Safety Notes

- Do not commit `.mewcode/config.yaml`.
- Prefer environment variables for API keys.
- Review permission mode before allowing file edits or shell commands.
- Keep `config.example.yaml` free of real credentials.
