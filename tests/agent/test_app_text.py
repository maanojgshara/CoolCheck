"""Static checks on the App's wording (src/app.py is a Streamlit page, so it is read as text, not run)."""
from pathlib import Path

APP = (Path(__file__).resolve().parents[2] / "src" / "app.py").read_text(encoding="utf-8")


def test_tool_calls_list_shows_every_call_and_the_rows_of_each_that_ran():
    # 25 Oct: refused calls are on the record too; the rows were shown once, for the last call only, under the checks
    assert "st.markdown(c.line())\n            if not c.error:  # a call that failed or was refused has no rows\n" \
           "                st.json(c.rows, expanded=False)\n        if d.checks:\n" in APP


def test_street_hint_says_a_street_can_be_written_either_way():
    # find_refuges and what_if_add_refuge read the street as people write it since 24 Oct, 23:36 (window D)
    assert "Street, as people write it (e.g. Jalan Kukoh or JLN KUKOH)" in APP
    assert "HDB abbreviations" not in APP
