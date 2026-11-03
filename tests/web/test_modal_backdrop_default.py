"""Modal backdrop: adjustable everywhere, and solid by default without wallpapers."""

from __future__ import annotations

import pytest

from core.web.routes import preferences


@pytest.mark.parametrize(
    ("enabled", "stored", "shown"),
    [
        (False, 48, 75),  # never adjusted, no wallpapers: nothing shows through
        (False, 30, 30),  # chosen: kept
        (False, 80, 80),
        (True, 48, 48),  # wallpapers on: the default stays
        (True, 30, 30),
    ],
)
def test_the_backdrop_shown(monkeypatch, enabled, stored, shown) -> None:
    monkeypatch.setattr(preferences, "theme_enabled", lambda: enabled)

    result = preferences._shown({"modal_backdrop_opacity": stored, "background_opacity": 90})

    assert result["modal_backdrop_opacity"] == shown


def test_wallpaper_choices_are_still_hidden_without_wallpapers(monkeypatch) -> None:
    monkeypatch.setattr(preferences, "theme_enabled", lambda: False)

    assert preferences._shown({"background_opacity": 90})["background_opacity"] == 35


def test_saving_without_wallpapers_keeps_the_chosen_backdrop() -> None:
    # The save route restores these from the database when wallpapers are off.
    assert "modal_backdrop_opacity" not in preferences.WALLPAPER_DEFAULTS
