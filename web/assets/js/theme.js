// AVA colour mode toggle: flips data-bs-theme on <html> and remembers the choice.
(function () {
  const btn = document.getElementById('avaTheme');
  if (!btn) return;
  const root = document.documentElement;
  const meta = document.querySelector('meta[name=theme-color]');
  const sync = () => {
    const light = root.getAttribute('data-bs-theme') === 'light';
    const label = light ? 'Switch to dark mode' : 'Switch to light mode';
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.setAttribute('aria-pressed', String(light));
    if (meta) meta.content = light ? '#F7F6F2' : '#0A1628';
  };
  btn.addEventListener('click', () => {
    const next = root.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-bs-theme', next);
    try { localStorage.setItem('ava-theme', next); } catch (e) { /* private mode: not remembered */ }
    sync();
  });
  sync();
})();
