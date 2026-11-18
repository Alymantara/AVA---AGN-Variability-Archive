// Crosshair tooltip for the redshift panels on calibration.php (.ava-cal-zwrap[data-zscan]).
(() => {
  document.querySelectorAll('.ava-cal-zwrap[data-zscan]').forEach((wrap) => {
    const d = JSON.parse(wrap.dataset.zscan);
    const svg = wrap.querySelector('svg');
    const hit = svg.querySelector('.hit');
    const xh = svg.querySelector('.xhair');
    const tip = document.createElement('div');
    tip.className = 'ava-tip';
    tip.hidden = true;
    wrap.appendChild(tip);
    const n = d.z.length;
    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const sx = (ev.clientX - r.left) * (d.W / r.width);             // SVG user units
      const f = Math.min(Math.max((sx - d.x0) / d.pw, 0), 1);
      const i = Math.round(f * (n - 1));
      const x = d.x0 + (i / (n - 1)) * d.pw;
      xh.setAttribute('x1', x); xh.setAttribute('x2', x); xh.setAttribute('visibility', 'visible');
      tip.replaceChildren();
      const head = document.createElement('strong');
      head.textContent = `${d.band} · z = ${d.z[i].toFixed(3)}`;
      tip.appendChild(head);
      d.series.forEach((s) => {
        const row = document.createElement('span');
        const sw = document.createElement('i');
        sw.style.background = s.c;
        row.appendChild(sw);
        const v = s.v[i];
        row.appendChild(document.createTextNode(`${s.name}: ${v === null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + ' mmag'}`));
        tip.appendChild(row);
      });
      tip.hidden = false;
      const px = (x / d.W) * r.width;
      tip.style.left = `${Math.min(Math.max(px, tip.offsetWidth / 2 + 4), r.width - tip.offsetWidth / 2 - 4)}px`;
      tip.style.top = `${(ev.clientY - r.top) - 12}px`;
    };
    const hide = () => { tip.hidden = true; xh.setAttribute('visibility', 'hidden'); };
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerleave', hide);
  });
})();
