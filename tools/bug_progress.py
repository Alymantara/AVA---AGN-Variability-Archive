#!/usr/bin/env python3
"""Count the open and done items of docs/notes/bug_checklist.md and write the progress table at its top.

    python tools/bug_progress.py            # rewrite the table between the progress markers
    python tools/bug_progress.py --print    # only print it

Open items are the ``- [ ]`` lines of the High / Medium / Low sections; done items are the IDs in bold on the ``- [x]``
lines of Done (``**B06 / B07**`` counts as two). The Monday agenda repeats checklist items and is not counted.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

CHECKLIST = Path(__file__).resolve().parents[1] / "docs" / "notes" / "bug_checklist.md"
START, END = "<!-- progress:start -->", "<!-- progress:end -->"
SECTIONS = ("High", "Medium", "Low")


def sections(text: str) -> dict[str, str]:
    out, name = {}, None
    for line in text.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            name = m.group(1).strip()
            out[name] = ""
        elif name:
            out[name] += line + "\n"
    return out


def done_ids(body: str) -> int:
    n = 0
    for line in body.splitlines():
        m = re.match(r"^- \[x\] \*\*(.+?)\*\*", line)
        if m:
            n += max(1, len([t for t in re.split(r"\s*/\s*", m.group(1)) if t.strip()]))
    return n


def table(text: str, today: str | None = None) -> str:
    sec = sections(text)
    open_ = {k: len(re.findall(r"^- \[ \]", sec.get(k, ""), re.M)) for k in SECTIONS}
    done = done_ids(sec.get("Done", ""))
    total_open = sum(open_.values())
    total = total_open + done
    pct = lambda n: f"{100 * n / total:.0f} %" if total else "–"   # noqa: E731
    rows = [f"| {k} | {open_[k]} | {pct(open_[k])} |" for k in SECTIONS]
    return "\n".join([
        START,
        f"**Progress** (updated {today or date.today().isoformat()} by `python tools/bug_progress.py`)",
        "",
        "| | Items | Share of all |",
        "|---|---:|---:|",
        *rows,
        f"| **Still to do** | **{total_open}** | **{pct(total_open)}** |",
        f"| Done | {done} | {pct(done)} |",
        f"| All items | {total} | |",
        END,
    ])


def update(path: Path = CHECKLIST, today: str | None = None) -> str:
    text = path.read_text()
    new = table(text, today)
    if START in text and END in text:
        text = text[:text.index(START)] + new + text[text.index(END) + len(END):]
    else:                                   # first time: after the title line
        head, _, rest = text.partition("\n")
        text = f"{head}\n\n{new}\n{rest}"
    path.write_text(text)
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--print", action="store_true", help="print the table, do not write the file")
    ap.add_argument("--file", type=Path, default=CHECKLIST)
    a = ap.parse_args(argv)
    print(table(a.file.read_text()) if a.print else update(a.file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
