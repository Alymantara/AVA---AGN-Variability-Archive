// Click-to-sort for tables whose header cells carry data-sort="text|num".
document.querySelectorAll('table').forEach((table) => {
  const heads = [...table.querySelectorAll('thead th[data-sort]')];
  const body = table.tBodies[0];
  heads.forEach((th) => {
    th.tabIndex = 0;
    const run = () => {
      const col = [...th.parentNode.children].indexOf(th);
      const dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
      heads.forEach((h) => h.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
      const val = (row) => {
        const cell = row.children[col];
        const raw = cell.dataset.v ?? cell.textContent.trim();
        if (th.dataset.sort === 'num') {
          const n = parseFloat(raw.replace(/,/g, ''));
          return Number.isNaN(n) ? -Infinity : n;
        }
        return raw.toLowerCase();
      };
      [...body.rows]
        .sort((a, b) => {
          const x = val(a), y = val(b);
          return (x < y ? -1 : x > y ? 1 : 0) * dir;
        })
        .forEach((r) => body.appendChild(r));
    };
    th.addEventListener('click', run);
    th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); } });
  });
});
