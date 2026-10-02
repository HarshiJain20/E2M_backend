import json

from app.core.config import ROOT_DIR, Settings, configuration_problems


def test_values_load_from_config_json(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "supabase": {"url": "https://abc.supabase.co", "publishable_key": "sb_publishable_test"},
        "ai_geometry": {"url": "http://gpu-box:8100"},
        "storage": {"max_file_size_mb": 12},
    }))
    monkeypatch.setenv("E2M_CONFIG_FILE", str(config))
    monkeypatch.delenv("E2M_SUPABASE__URL", raising=False)

    settings = Settings()

    assert settings.supabase.url == "https://abc.supabase.co"
    assert settings.supabase.publishable_key == "sb_publishable_test"
    assert settings.ai_geometry.url == "http://gpu-box:8100"
    assert settings.storage.max_file_size_mb == 12
    assert settings.storage.thumbnail_max_side == 480  # untouched keys keep defaults


def test_environment_overrides_config_json(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"ai_geometry": {"url": "http://from-file:8100", "timeout_seconds": 30}}))
    monkeypatch.setenv("E2M_CONFIG_FILE", str(config))
    monkeypatch.setenv("E2M_AI_GEOMETRY__URL", "http://from-env:8100")

    settings = Settings()

    assert settings.ai_geometry.url == "http://from-env:8100"
    assert settings.ai_geometry.timeout_seconds == 30


def test_missing_config_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("E2M_CONFIG_FILE", str(tmp_path / "absent.json"))
    monkeypatch.delenv("E2M_SUPABASE__URL", raising=False)

    settings = Settings()

    assert settings.supabase.url == ""
    assert settings.ai_geometry.url == "http://localhost:8100"


def test_example_config_is_valid():
    example = json.loads((ROOT_DIR / "config.example.json").read_text())
    Settings.model_validate(example)
    assert set(example) == set(Settings.model_fields)


def test_placeholder_config_is_reported():
    settings = Settings.model_validate({
        "supabase": {"url": "https://<project-ref>.supabase.co", "publishable_key": "sb_publishable_..."},
        "storage": {"backend": "supabase"},
    })

    problems = configuration_problems(settings)

    assert len(problems) == 2
    assert "supabase.url" in problems[0]
    assert "supabase.publishable_key" in problems[1]


def test_complete_config_has_no_problems():
    settings = Settings.model_validate({
        "supabase": {"url": "https://ref.supabase.co", "publishable_key": "sb_publishable_abc123"},
        "storage": {"backend": "supabase"},
    })

    assert configuration_problems(settings) == []
