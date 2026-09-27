"""worker.paths.rules_dir — env override > image /app/rules > checkout <repo>/rules."""

from pathlib import Path

from worker import paths


def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("REPODOC_RULES_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "APP_RULES_DIR", tmp_path / "app-rules")
    (tmp_path / "app-rules").mkdir()
    assert paths.rules_dir() == tmp_path


def test_image_rules_dir_used_when_present(tmp_path, monkeypatch):
    monkeypatch.delenv("REPODOC_RULES_DIR", raising=False)
    monkeypatch.setattr(paths, "APP_RULES_DIR", tmp_path)
    assert paths.rules_dir() == tmp_path


def test_checkout_rules_dir_is_the_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("REPODOC_RULES_DIR", raising=False)
    monkeypatch.setattr(paths, "APP_RULES_DIR", tmp_path / "missing")
    assert paths.rules_dir() == paths.REPO_RULES_DIR
    assert paths.REPO_RULES_DIR == Path(paths.__file__).resolve().parents[2] / "rules"
