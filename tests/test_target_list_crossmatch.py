"""Offline tests for tools/target_list_crossmatch.py (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import target_list_crossmatch as t  # noqa: E402


def test_norm_folds_aliases():
    assert t.norm("Mrk 1044") == t.norm("Mrk1044") == t.norm("MKN 1044")
    assert t.norm("Akn120") == t.norm("Ark 120")
    assert t.norm("NGC4395offset") == t.norm("NGC 4395")
    assert t.norm("Q0142-100_offs") == t.norm("Q0142-100")
    assert t.norm("I Zw 1") == t.norm("1Zw1")


def test_parse_list_aliases_and_none(tmp_path):
    p = tmp_path / "l.tsv"
    p.write_text("# header\nPG 0844+349\t131.92\t34.75\tagn\t0.064\t125\nPG 0844+349 Ton 951\t\t\t\t\t\n"
                 "J1421+3855\t215.27\t38.92\tagn\t0.489\t9\nJ1421+3855 J1421+3855 J1421+3855\t\t\t\t\t\n"
                 "Mrk9\t114.23\t58.77\tLAMP\tNone\t151\n")
    d = t.parse_list(p)
    assert list(d["list_name"]) == ["PG 0844+349", "J1421+3855", "Mrk9"]
    assert d["aliases"][0] == ["Ton 951"]
    assert d["aliases"][1] == []  # repeated own name is not an alias
    assert d["list_z"].isna()[2] and d["list_epochs"][2] == 151
