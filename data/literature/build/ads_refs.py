"""ADS helpers: resolve free-text references to bibcodes and bibcodes to short citations (cached).

Token: ~/.ads/dev_key. Cache: cache/ads_cache.json (query -> result), so re-runs make no requests.
"""
import json, re, time, urllib.parse, urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "cache" / "ads_cache.json"
_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
_tok = None
JOUR = {"ApJ": "ApJ", "ApJS": "ApJS", "ApJL": "ApJL", "MNRAS": "MNRAS", "A&A": "A&A", "AJ": "AJ", "PASP": "PASP", "Nature": "Natur"}


def _q(q, fl="bibcode,first_author,author_count,year,author"):
    global _tok
    key = f"{q}|{fl}"
    if key in _cache:
        return _cache[key]
    _tok = _tok or (Path.home() / ".ads/dev_key").read_text().strip()
    url = "https://api.adsabs.harvard.edu/v1/search/query?" + urllib.parse.urlencode(dict(q=q, fl=fl, rows=5))
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_tok}"})
    docs = json.loads(urllib.request.urlopen(req, timeout=60).read())["response"]["docs"]
    _cache[key] = docs
    CACHE.write_text(json.dumps(_cache, indent=0))
    time.sleep(0.2)
    return docs


def resolve(text):
    """'Peterson et al. 1998 ApJ, 501, 82' -> bibcode (or None). Uses the first citation in the string."""
    m = re.search(r"([A-Z][A-Za-z'\-]+(?: [A-Z][a-z]+)?)(?: et al\.| & [A-Z][A-Za-z\-]+)?,? (\d{4})\s+([A-Z][A-Za-z&]+)\s*,?\s*(\d+)\s*,\s*L?(\d+)", text or "")
    if not m:
        return None
    au, y, j, v, p = m.groups()
    au = au.replace("Santos-Lleo", "Santos-Lle")
    docs = _q(f'author:"^{au}" year:{y} volume:{v} page:{p}')
    if not docs:   # author spelling differs (accents etc.): accept only an unambiguous year/volume/page match
        docs = _q(f'year:{y} volume:{v} page:{p} bibstem:"{JOUR.get(j, j)}"') or _q(f"year:{y} volume:{v} page:{p}")
        return docs[0]["bibcode"] if len(docs) == 1 else None
    return docs[0]["bibcode"]


def cite(bibcode):
    """bibcode -> 'Kara et al. (2021)' / 'Bentz & Katz (2015)'."""
    if not bibcode or not re.match(r"^\d{4}\S{15}$", bibcode):
        return None
    docs = _q(f'bibcode:"{bibcode}"')
    if not docs:
        return None
    d = docs[0]; a = [x.split(",")[0] for x in d.get("author", [])]
    if not a:
        return None
    s = a[0] if len(a) == 1 else (f"{a[0]} & {a[1]}" if len(a) == 2 else f"{a[0]} et al.")
    return f"{s} ({d['year']})"
