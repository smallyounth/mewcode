from __future__ import annotations

from pathlib import Path

from mewcode.config import load_config
from mewcode.setup_wizard import (
    SetupAnswers,
    any_config_exists,
    build_config_yaml,
    missing_api_key_envs,
    run_setup_wizard,
    write_config_file,
)


def test_builds_deepseek_config_with_env_var() -> None:
    text = build_config_yaml(
        SetupAnswers(
            provider="deepseek",
            model="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
        )
    )

    assert "protocol: openai-compat" in text
    assert "base_url: https://api.deepseek.com" in text
    assert "model: deepseek-chat" in text
    assert "api_key: ${DEEPSEEK_API_KEY}" in text


def test_builds_custom_openai_compatible_config() -> None:
    text = build_config_yaml(
        SetupAnswers(
            provider="custom",
            name="moonshot",
            protocol="openai-compat",
            base_url="https://api.moonshot.cn/v1",
            model="kimi-k2",
            api_key_env="MOONSHOT_API_KEY",
            context_window=128000,
            max_output_tokens=4096,
        )
    )

    assert "name: moonshot" in text
    assert "base_url: https://api.moonshot.cn/v1" in text
    assert "model: kimi-k2" in text
    assert "context_window: 128000" in text
    assert "max_output_tokens: 4096" in text


def test_written_config_loads(tmp_path: Path) -> None:
    config_path = tmp_path / ".mewcode" / "config.yaml"
    write_config_file(
        config_path,
        SetupAnswers(
            provider="openai",
            model="gpt-4.1",
            api_key_env="OPENAI_API_KEY",
        ),
    )

    cfg = load_config(config_path)
    assert cfg.providers[0].name == "openai"
    assert cfg.providers[0].protocol == "openai"
    assert cfg.providers[0].model == "gpt-4.1"


def test_direct_api_key_is_written_when_requested() -> None:
    text = build_config_yaml(
        SetupAnswers(
            provider="deepseek",
            model="deepseek-chat",
            direct_api_key="sk-test",
        )
    )

    assert "api_key: sk-test" in text
    assert "${DEEPSEEK_API_KEY}" not in text


def test_detects_project_and_home_config(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    cwd.mkdir()
    home.mkdir()

    assert any_config_exists(cwd=cwd, home=home) is False

    home_config = home / ".mewcode" / "config.yaml"
    home_config.parent.mkdir()
    home_config.write_text("providers: []", encoding="utf-8")
    assert any_config_exists(cwd=cwd, home=home) is True


def test_missing_api_key_envs_detects_unset_refs(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    cfg = load_config(
        Path("config.example.yaml")
    )
    cfg.providers[0].api_key = "${MISSING_KEY}"

    assert missing_api_key_envs(cfg.providers) == [("deepseek", "MISSING_KEY")]


def test_missing_api_key_envs_accepts_set_refs(monkeypatch) -> None:
    monkeypatch.setenv("PRESENT_KEY", "secret")
    cfg = load_config(
        Path("config.example.yaml")
    )
    cfg.providers[0].api_key = "${PRESENT_KEY}"

    assert missing_api_key_envs(cfg.providers) == []


def test_setup_wizard_does_not_overwrite_when_cancelled(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / ".mewcode" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text("existing", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    assert run_setup_wizard(config_path, force=True) is False
    assert config_path.read_text(encoding="utf-8") == "existing"
