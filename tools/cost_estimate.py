"""Hours used per semester (observation portal) and their value at LCO list prices.

  python3 tools/cost_estimate.py [--usd-1m 450] [--usd-2m 900] [--gbp-per-usd 0.746] [--csv out.csv]

1 m: LCO network-time price for >=100 h/yr (lco.global/observatory/sales/networktime), USD 450/h.
2 m: not sold by LCO; --usd-2m is an assumption (default 2x the 1 m rate).
Prices are today's list prices applied to all semesters (no inflation / historical rates).
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ava.lcodb.api import Client          # noqa: E402
from ava.lcodb.config import load_config  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--usd-1m', type=float, default=450.0)
    p.add_argument('--usd-2m', type=float, default=900.0)
    p.add_argument('--gbp-per-usd', type=float, default=0.746)
    p.add_argument('--prefix', default='KEY')
    p.add_argument('--csv')
    a = p.parse_args()
    cfg = load_config()
    c = Client(cfg.token)
    rows = []
    for prop in c.proposals():
        if not prop['id'].startswith(a.prefix):
            continue
        for t in prop.get('timeallocation_set', []):
            inst = t.get('instrument_type') or (t.get('instrument_types') or ['?'])[0]
            tel = inst[:3]   # 1M0 / 2M0 / 0M4
            used = sum(t.get(k) or 0 for k in ('std_time_used', 'rr_time_used', 'tc_time_used'))
            alloc = sum(t.get(k) or 0 for k in ('std_allocation', 'rr_allocation', 'tc_allocation'))
            rate = {'1M0': a.usd_1m, '2M0': a.usd_2m}.get(tel, 300.0)
            rows.append(dict(proposal=prop['id'].rstrip('f') if False else prop['id'], semester=t['semester'],
                             instrument=inst, telescope=tel, allocated_h=alloc, used_h=used,
                             usd=used * rate, gbp=used * rate * a.gbp_per_usd))
    rows.sort(key=lambda r: (r['proposal'], r['semester'], r['instrument']))
    if a.csv:
        with open(a.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    def table(key):
        agg = defaultdict(lambda: defaultdict(float))
        for r in rows:
            k = key(r)
            agg[k][r['telescope'] + '_h'] += r['used_h']
            agg[k]['alloc'] += r['allocated_h']
            agg[k]['used'] += r['used_h']
            agg[k]['usd'] += r['usd']
            agg[k]['gbp'] += r['gbp']
        return agg

    print(f"rates: 1m ${a.usd_1m:.0f}/h, 2m ${a.usd_2m:.0f}/h (assumed), GBP/USD {a.gbp_per_usd}\n")
    hdr = f"{'':22s} {'1m used h':>10s} {'2m used h':>10s} {'used/alloc':>11s} {'USD':>12s} {'GBP':>12s}"
    for title, key in (('per project', lambda r: r['proposal']),
                       ('per project and semester', lambda r: f"{r['proposal']} {r['semester']}")):
        print(f'== {title}\n{hdr}')
        agg = table(key)
        tot = defaultdict(float)
        for k in sorted(agg):
            v = agg[k]
            if v['alloc'] == 0 and v['used'] == 0:
                continue
            for kk, vv in v.items():
                tot[kk] += vv
            print(f"{k:22s} {v['1M0_h']:10.0f} {v['2M0_h']:10.0f} {v['used']:5.0f}/{v['alloc']:<5.0f} "
                  f"{v['usd']:12,.0f} {v['gbp']:12,.0f}")
        print(f"{'TOTAL':22s} {tot['1M0_h']:10.0f} {tot['2M0_h']:10.0f} {tot['used']:5.0f}/{tot['alloc']:<5.0f} "
              f"{tot['usd']:12,.0f} {tot['gbp']:12,.0f}\n")


if __name__ == '__main__':
    main()
