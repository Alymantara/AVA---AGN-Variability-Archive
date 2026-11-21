import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bug_progress  # noqa: E402

TEXT = """# Checklist

intro

## Monday agenda
- [ ] **B33** again (not counted)

## High
- [ ] **B1** a
  more
- [ ] **B2** b

## Medium
- [ ] **B3** c

## Low

## Done
- [x] **B4** d
- [x] **B6 / B7** e
"""


def test_table_counts_and_rewrites_in_place(tmp_path):
    f = tmp_path / "c.md"
    f.write_text(TEXT)
    t = bug_progress.update(f, today="2026-11-21")
    assert "| High | 2 | 33 % |" in t and "| Low | 0 | 0 % |" in t
    assert "| **Still to do** | **3** | **50 %** |" in t and "| Done | 3 | 50 % |" in t
    first = f.read_text()
    assert first.startswith("# Checklist\n\n" + bug_progress.START)
    bug_progress.update(f, today="2026-11-22")                   # idempotent: one table, replaced
    assert f.read_text().count(bug_progress.START) == 1 and "2026-11-22" in f.read_text()
