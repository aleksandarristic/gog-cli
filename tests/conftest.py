from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_aria2c_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests deterministic regardless of whether aria2c happens to be
    installed on the machine running them (gog-cli auto-selects aria2c when
    present). Tests that specifically exercise aria2c detection/selection
    already patch shutil.which themselves, which takes precedence for the
    scope of their own `with patch(...)` block.
    """
    monkeypatch.setattr("shutil.which", lambda _name: None)
