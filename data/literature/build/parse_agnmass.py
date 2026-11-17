"""Parse the cached AGN Black Hole Mass Database pages (Bentz & Katz 2015) into JSON."""
import re, html, json, sys
from pathlib import Path
d = Path(sys.argv[1]); out = []
MB = r'([\d.]+) \( ?\+ ?([\d.]+) ?/ ?- ?([\d.]+) ?\) \(10 (\d+) M sun \)'
def mb(m): return None if not m else dict(m=float(m.group(1)), ep=float(m.group(2)), em=float(m.group(3)), exp=int(m.group(4)))
for f in sorted(d.glob('d*.html'), key=lambda p: int(p.stem[1:])):
    vid = int(f.stem[1:]); t = re.sub(r'(?s)<(script|style).*?</\1>', '', f.read_text(errors='ignore'))
    txt = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
    name = re.search(r'AGN Black Hole Mass Database\s+(\S+)', txt).group(1)
    z = float(re.search(r'z = ([\d.]+)', txt).group(1))
    ra = re.search(r'RA = (\S+) Dec = (\S+)', txt)
    i = txt.find('only):'); ms = list(re.finditer(MB, txt[i:i + 400])) if i >= 0 else []
    j = txt.find('RM modeling):'); mod = re.search(MB + r'\s*(.{0,60}?)\s*(Reverberation|$)', txt[j:j + 400]) if j >= 0 else None
    rows = []
    for tr in re.findall(r'(?s)<tr.*?</tr>', t):
        cells = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip() for c in re.findall(r'(?s)<td.*?</td>', tr)]
        if len(cells) >= 11 and 'λ' in cells[0]:
            rows.append(dict(line=cells[0], jd=cells[1], tau_jav=cells[2], jav_ref=cells[3], tau_cent=cells[4], tau_peak=cells[5],
                             sigma=cells[6], fwhm=cells[7], rm_ref=cells[8], logL=cells[9], L_ref=cells[10]))
    out.append(dict(vid=vid, name=name, z=z, ra=ra.group(1), dec=ra.group(2),
                    mbh_hb=mb(ms[0]) if ms else None, mbh_all=mb(ms[1]) if len(ms) > 1 else None,
                    mbh_model=mb(mod), model_ref=mod.group(5).strip() if mod else None, rows=rows))
json.dump(out, open(sys.argv[2], 'w'), indent=1, ensure_ascii=False)
print(len(out), 'objects;', sum(1 for o in out if o['mbh_hb']), 'with Hb mass')
