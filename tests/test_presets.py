import pytest
from film_date_agent.presets import (
    slugify,
    get_builtin_presets,
    list_all_presets,
    resolve_preset,
    create_preset,
)
from film_date_agent.errors import AgentError


def test_slugify():
    assert slugify("Japanese Tokyo 90s") == "japanese-tokyo-90s"
    assert slugify("FDS7_Strict_Compact (80s -7°)") == "fds7-strict-compact-80s-7"
    assert slugify("Arcane Occult (Crimson Script)") == "arcane-occult-crimson-script"


def test_builtin_presets_count():
    presets = get_builtin_presets()
    assert len(presets) >= 12
    assert "Japanese Tokyo 90s" in presets
    assert "Japanese Snap (Disposable)" in presets


def test_resolve_favorite():
    resolved = resolve_preset("favorite")
    assert resolved.slug == "japanese-tokyo-90s"
    assert resolved.name == "Japanese Tokyo 90s"


def test_resolve_alias():
    resolved = resolve_preset("utsurun")
    assert resolved.slug == "japanese-snap-disposable"


def test_resolve_unknown_raises():
    with pytest.raises(AgentError) as exc:
        resolve_preset("non_existent_preset_xyz")
    assert exc.value.code == "preset_not_found"


def test_create_user_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("FILM_DATE_AGENT_CONFIG_DIR", str(tmp_path))
    res = create_preset(
        "My Custom 90s",
        {"preset_color": "Cyber Green", "show_time": True},
        base_name="japanese-tokyo-90s",
    )
    assert res["ok"] is True
    assert res["slug"] == "my-custom-90s"

    # 解決できることを確認
    resolved = resolve_preset("my-custom-90s")
    assert resolved.name == "My Custom 90s"
    assert resolved.config_dict["preset_color"] == "Cyber Green"
    assert resolved.config_dict["show_time"] is True
