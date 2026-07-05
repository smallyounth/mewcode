from __future__ import annotations

import getpass
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(".mewcode") / "config.yaml"


@dataclass
class ProviderPreset:
    name: str
    protocol: str
    base_url: str
    model: str
    api_key_env: str
    context_window: int = 0
    max_output_tokens: int = 8192


@dataclass
class SetupAnswers:
    provider: str
    model: str
    api_key_env: str = ""
    direct_api_key: str = ""
    name: str = ""
    protocol: str = ""
    base_url: str = ""
    context_window: int = 0
    max_output_tokens: int = 8192


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset(
        name="deepseek",
        protocol="openai-compat",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "openai": ProviderPreset(
        name="openai",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4.1",
        api_key_env="OPENAI_API_KEY",
    ),
    "anthropic": ProviderPreset(
        name="anthropic",
        protocol="anthropic",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    ),
}

VALID_PROTOCOLS = ("anthropic", "openai", "openai-compat")
_ENV_REF_RE = re.compile(r"^\$\{([^}]+)\}$")
_DEFAULT_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compat": "OPENAI_API_KEY",
}


def _clean_int(value: int, default: int = 0) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def build_config_dict(answers: SetupAnswers) -> dict:
    preset = PROVIDER_PRESETS.get(answers.provider)
    name = answers.name or (preset.name if preset else "custom")
    protocol = answers.protocol or (preset.protocol if preset else "openai-compat")
    base_url = answers.base_url or (preset.base_url if preset else "")
    model = answers.model or (preset.model if preset else "")
    api_key_env = answers.api_key_env or (preset.api_key_env if preset else "API_KEY")
    api_key = answers.direct_api_key or f"${{{api_key_env}}}"

    return {
        "providers": [
            {
                "name": name,
                "protocol": protocol,
                "base_url": base_url,
                "model": model,
                "api_key": api_key,
                "context_window": _clean_int(answers.context_window),
                "max_output_tokens": _clean_int(answers.max_output_tokens, 8192),
            }
        ],
        "permission_mode": "default",
        "enable_fork": False,
        "enable_verification_agent": False,
        "teammate_mode": "",
        "enable_coordinator_mode": False,
    }


def build_config_yaml(answers: SetupAnswers) -> str:
    data = build_config_dict(answers)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def write_config_file(path: Path, answers: SetupAnswers) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_config_yaml(answers), encoding="utf-8")


def any_config_exists(cwd: Path | None = None, home: Path | None = None) -> bool:
    cwd = cwd or Path.cwd()
    home = home or Path.home()
    return any(
        path.exists()
        for path in (
            home / ".mewcode" / "config.yaml",
            cwd / ".mewcode" / "config.yaml",
            cwd / ".mewcode" / "config.local.yaml",
        )
    )


def missing_api_key_envs(providers: list[Any]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for provider in providers:
        name = getattr(provider, "name", "provider")
        protocol = getattr(provider, "protocol", "")
        raw_key = getattr(provider, "api_key", "") or ""

        env_name = ""
        match = _ENV_REF_RE.fullmatch(raw_key)
        if match:
            env_name = match.group(1)
        elif not raw_key:
            env_name = _DEFAULT_API_KEY_ENV.get(protocol, "")

        if env_name and not os.environ.get(env_name):
            missing.append((name, env_name))

    return missing


def print_missing_api_key_help(missing: list[tuple[str, str]]) -> None:
    print("MewCode is configured, but one or more API key variables are missing.")
    for provider_name, env_name in missing:
        print(f"  - provider '{provider_name}' needs {env_name}")
    print("")
    print("Set the environment variable before starting MewCode, or run:")
    print("  mewcode --setup")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        print("")
        return default
    return value or default


def _ask_int(prompt: str, default: int) -> int:
    raw = _ask(prompt, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _ask_provider() -> str:
    print("Choose a model provider:")
    print("  1) DeepSeek")
    print("  2) OpenAI")
    print("  3) Anthropic")
    print("  4) Custom OpenAI-compatible provider")
    choice = _ask("Provider", "1").lower()
    return {
        "1": "deepseek",
        "2": "openai",
        "3": "anthropic",
        "4": "custom",
        "deepseek": "deepseek",
        "openai": "openai",
        "anthropic": "anthropic",
        "custom": "custom",
    }.get(choice, "deepseek")


def _ask_api_key(env_name: str) -> tuple[str, str]:
    existing = os.environ.get(env_name, "")
    if existing:
        print(f"Found environment variable {env_name}; the config will reference it.")
        return env_name, ""

    print(
        "Recommended: store your API key in an environment variable, "
        "then keep only ${ENV_NAME} in the config file."
    )
    choice = _ask("Save API key as environment variable reference? (Y/n)", "Y").lower()
    if choice not in {"n", "no"}:
        env_name = _ask("Environment variable name", env_name)
        return env_name, ""

    try:
        direct_key = getpass.getpass(
            "API key (will be saved in .mewcode/config.yaml): "
        ).strip()
    except EOFError:
        direct_key = ""
    return "", direct_key


def prompt_for_answers() -> SetupAnswers | None:
    provider = _ask_provider()
    preset = PROVIDER_PRESETS.get(provider)

    if provider == "custom":
        name = _ask("Provider name", "custom")
        protocol = _ask("Protocol", "openai-compat")
        if protocol not in VALID_PROTOCOLS:
            protocol = "openai-compat"
        base_url = _ask("Base URL", "https://api.example.com/v1")
        model = _ask("Model", "")
        api_key_env_default = f"{name.upper().replace('-', '_')}_API_KEY"
    else:
        assert preset is not None
        name = preset.name
        protocol = preset.protocol
        base_url = preset.base_url
        model = _ask("Model", preset.model)
        api_key_env_default = preset.api_key_env

    api_key_env, direct_api_key = _ask_api_key(api_key_env_default)
    context_window = _ask_int("Context window (0 = auto/fallback)", 0)
    max_output_tokens = _ask_int("Max output tokens", 8192)

    return SetupAnswers(
        provider=provider,
        name=name,
        protocol=protocol,
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        direct_api_key=direct_api_key,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )


def run_setup_wizard(path: Path = DEFAULT_CONFIG_PATH, *, force: bool = False) -> bool:
    if path.exists() and not force:
        print(f"Config already exists: {path}")
        print("Run `mewcode --setup` to reconfigure.")
        return True
    if path.exists() and force:
        choice = _ask(f"Config already exists at {path}. Overwrite? (y/N)", "N")
        if choice.lower() not in {"y", "yes"}:
            print("Setup cancelled. Existing config was not changed.")
            return False

    print("MewCode needs a model provider before starting.")
    print("This will create a local config file at .mewcode/config.yaml.")
    answers = prompt_for_answers()
    if answers is None:
        return False

    write_config_file(path, answers)
    print(f"Config written to {path}")
    if answers.api_key_env and not os.environ.get(answers.api_key_env):
        print(f"Set {answers.api_key_env} in your shell before running MewCode.")
    return True
