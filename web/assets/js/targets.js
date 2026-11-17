// Targets page: card/classic view toggle, search, status and campaign filters, card sort.
(() => {
  const root = document.documentElement;
  const grid = document.getElementById('grid');
  if (!grid) return;
  const cards = [...grid.querySelectorAll('.ava-card')];
  const rows = [...document.querySelectorAll('#classic tbody tr')];
  const q = document.getElementById('q');
  const sort = document.getElementById('sort');
  const count = document.getElementById('count');
  const empty = document.getElementById('empty');
  const status = () => document.querySelector('input[name=status]:checked').value;
  const campaign = document.getElementById('campaign');

  // ---- view toggle (remembered per browser, shareable via ?view=) ----
  const setView = (v, push) => {
    root.dataset.view = v;
    document.getElementById(`v-${v}`).checked = true;
    try { localStorage.setItem('ava-view', v); } catch (e) { /* private mode */ }
    if (push) {
      const u = new URL(location.href);
      u.searchParams.set('view', v);
      history.replaceState(null, '', u);
    }
  };
  setView(root.dataset.view === 'modern' ? 'modern' : 'classic', false);
  document.querySelectorAll('input[name=view]').forEach((r) =>
    r.addEventListener('change', () => setView(r.value, true)));

  // ---- search + status filter (applies to both views) ----
  const sorters = {
    name: (a, b) => a.dataset.name.localeCompare(b.dataset.name, undefined, { numeric: true }),
    z: (a, b) => (parseFloat(a.dataset.z) || 0) - (parseFloat(b.dataset.z) || 0),
    frames: (a, b) => (+b.dataset.frames) - (+a.dataset.frames),
  };

  function apply() {
    const term = q.value.trim().toLowerCase().replace(/\s+/g, ' ');
    const st = status();
    const cp = campaign.value;
    const match = (el) => (st === 'all' || el.dataset.status === st)
      && (cp === 'all' || el.dataset.campaign === cp)
      && (!term || el.dataset.name.includes(term));
    let n = 0;
    for (const c of cards) { const s = match(c); c.hidden = !s; if (s) n++; }
    for (const r of rows) r.hidden = !match(r);
    count.textContent = `${n} target${n === 1 ? '' : 's'}`;
    empty.hidden = n > 0;
  }

  q.addEventListener('input', apply);
  campaign.addEventListener('change', apply);
  document.querySelectorAll('input[name=status]').forEach((r) => r.addEventListener('change', apply));
  sort.addEventListener('change', () => cards.sort(sorters[sort.value]).forEach((c) => grid.appendChild(c)));
})();
