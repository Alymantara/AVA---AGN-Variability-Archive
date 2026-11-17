import re
NUM = r"(-?[\d.]+)"


def num(s):
    m = re.match(r"\s*" + NUM, str(s or ""))
    return float(m.group(1)) if m and m.group(1) not in (".", "...") else None


def pm(s):
    """'20.9 ( + 2.3 / - 2.3 )' -> (20.9, mean err); '43.73 (+/- 0.05)' -> (43.73, 0.05)."""
    s = str(s or "")
    v = num(s)
    if v is None:
        return None, None
    m = re.search(r"\+\s*([\d.]+)\s*/\s*-\s*([\d.]+)", s)
    if m:
        return v, round((float(m.group(1)) + float(m.group(2))) / 2, 3)
    m = re.search(r"\+/-\s*([\d.]+)", s)
    return v, (float(m.group(1)) if m else None)
