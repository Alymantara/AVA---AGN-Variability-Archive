// Target page: show the coordinates in h:m:s or degrees (remembered in this browser).
(() => {
  const table = document.getElementById('coords');
  if (!table) return;
  const KEY = 'ava-coord-units';
  const set = (u) => {
    table.classList.toggle('is-deg', u === 'deg');
    const r = document.getElementById(u === 'deg' ? 'cu-deg' : 'cu-hms');
    if (r) r.checked = true;
  };
  try { set(localStorage.getItem(KEY) || 'hms'); } catch (e) { set('hms'); }
  table.querySelectorAll('input[name="coord-units"]').forEach((r) => r.addEventListener('change', () => {
    if (!r.checked) return;
    set(r.value);
    try { localStorage.setItem(KEY, r.value); } catch (e) { /* private window */ }
  }));
})();
