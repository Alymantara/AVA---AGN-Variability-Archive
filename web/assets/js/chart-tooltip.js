// Hover / focus tooltip for server-rendered SVG charts (.ava-chart a.pt with data-*).
(() => {
  document.querySelectorAll('.ava-chart-wrap').forEach((wrap) => {
    const tip = document.createElement('div');
    tip.className = 'ava-tip';
    tip.hidden = true;
    wrap.appendChild(tip);
    const show = (a) => {
      const d = a.dataset;
      tip.innerHTML = `<strong></strong><span></span><span></span>`;
      tip.children[0].textContent = d.name;
      tip.children[1].textContent = `log M ${d.m} · log L ${d.l}`;
      tip.children[2].textContent = `L/LEdd ${d.edd} · ${d.status}`;
      const r = a.querySelector('.dot').getBoundingClientRect();
      const w = wrap.getBoundingClientRect();
      tip.hidden = false;
      const x = r.left + r.width / 2 - w.left;
      tip.style.left = `${Math.min(Math.max(x, tip.offsetWidth / 2 + 4), w.width - tip.offsetWidth / 2 - 4)}px`;
      tip.style.top = `${r.top - w.top - 10}px`;
      wrap.querySelectorAll('a.pt.on').forEach((o) => o.classList.remove('on'));
      a.classList.add('on');
    };
    const hide = () => { tip.hidden = true; wrap.querySelectorAll('a.pt.on').forEach((o) => o.classList.remove('on')); };
    wrap.querySelectorAll('a.pt').forEach((a) => {
      a.querySelector('title')?.remove();          // the custom tooltip replaces the native one
      a.addEventListener('mouseenter', () => show(a));
      a.addEventListener('focus', () => show(a));
      a.addEventListener('mouseleave', hide);
      a.addEventListener('blur', hide);
    });
  });
})();
