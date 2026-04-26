from pathlib import Path

import bootstrap


def test_upsert_env_replaces_existing_value(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BH_AGENT_API_KEY=old\nOTHER=1\n")

    bootstrap.upsert_env(env, "BH_AGENT_API_KEY", "new value")

    text = env.read_text()
    assert "BH_AGENT_API_KEY='new value'" in text
    assert "OTHER=1" in text


def test_install_codex_skill_is_idempotent(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("# skill")
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    assert bootstrap.install_codex_skill(repo)
    assert bootstrap.install_codex_skill(repo)

    link = codex_home / "skills" / "browser-harness" / "SKILL.md"
    assert link.is_symlink()
    assert link.resolve() == (repo / "SKILL.md").resolve()


def test_install_claude_import_is_idempotent(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("# skill")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert bootstrap.install_claude_import(repo)
    assert bootstrap.install_claude_import(repo)

    text = (tmp_path / ".claude" / "CLAUDE.md").read_text()
    line = f"@{repo / 'SKILL.md'}"
    assert text.count(line) == 1


def test_configure_provider_uses_existing_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BH_AGENT_API_KEY", "key")

    assert bootstrap.configure_provider(tmp_path, no_save=True)
