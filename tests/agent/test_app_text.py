"""Static checks on the App's wording (src/app.py is a Streamlit page, so it is read as text, not run)."""
from pathlib import Path

APP = (Path(__file__).resolve().parents[2] / "src" / "app.py").read_text(encoding="utf-8")


def test_street_hint_says_a_street_can_be_written_either_way():
    # find_refuges and what_if_add_refuge read the street as people write it since 24 Oct, 23:36 (window D)
    assert "Street, as people write it (e.g. Jalan Kukoh or JLN KUKOH)" in APP
    assert "HDB abbreviations" not in APP
