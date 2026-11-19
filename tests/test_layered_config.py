"""A machine's config as overrides on top of the repository template (ava.utils.layered_config, tools/make_config.py)."""
import textwrap

from ava.utils.layered_config import deep_merge, flatten, load_layered


def test_overrides_merge_onto_the_template(tmp_path):
    t = tmp_path / "tmpl" / "ava_config.yaml"
    t.parent.mkdir()
    t.write_text(textwrap.dedent("""
        paths: {archive_root: data/archive, logs: data/logs}
        pipeline: {n_cores: 1, prefect: {nightly_steps: [a, b], schedule_cron: "0 2 * * *"}}
        new_section: {added_later: true}
    """))
    o = tmp_path / "data" / "config" / "ava_config.yaml"
    o.parent.mkdir(parents=True)
    o.write_text("base: ../../tmpl/ava_config.yaml\npaths: {archive_root: /x/archive}\npipeline: {n_cores: 4}\n")
    merged, base = load_layered(o)
    assert base == t.resolve()
    assert merged["paths"] == {"archive_root": "/x/archive", "logs": "data/logs"}       # nested sections merge
    assert merged["pipeline"]["n_cores"] == 4 and merged["pipeline"]["prefect"]["nightly_steps"] == ["a", "b"]
    assert merged["new_section"]["added_later"] is True                                # template keys arrive
    full = tmp_path / "full.yaml"
    full.write_text("paths: {archive_root: y}\n")
    assert load_layered(full) == ({"paths": {"archive_root": "y"}}, None)              # a full copy as before


def test_lcodb_overrides_keep_template_relative_paths(tmp_path, monkeypatch):
    from ava.lcodb import config as L
    o = tmp_path / "lcodb_config.yaml"
    o.write_text(f"base: {L.DEFAULT_CONFIG}\ntoken_file: /nonexistent/token\n")
    monkeypatch.delenv("LCO_TOKEN", raising=False)
    monkeypatch.delenv("LCO_API_TOKEN", raising=False)
    c = L.load_config(o)
    assert c.path == o and c.raw["token_file"] == "/nonexistent/token"
    # db_dir ../data/lcodb of the template stays relative to config/, not to this file's folder
    assert c.resolve(c.raw["db_dir"]) == (L.DEFAULT_CONFIG.parent / c.raw["db_dir"]).resolve()


def test_deep_merge_and_flatten():
    assert deep_merge({"a": {"b": 1, "c": 2}, "d": [1]}, {"a": {"c": 3}, "d": [2]}) == {"a": {"b": 1, "c": 3}, "d": [2]}
    assert flatten({"a": {"b": 1}, "c": [1, 2]}) == {"a.b": 1, "c": [1, 2]}
