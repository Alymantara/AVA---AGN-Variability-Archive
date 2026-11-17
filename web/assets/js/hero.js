// Landing hero: slow cross-fade through the diluted target images; the caption follows.
(function () {
  const imgs = [...document.querySelectorAll('.ava-hero__bg img')];
  const credit = document.getElementById('heroCredit');
  if (imgs.length < 2 || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const load = (img) => { if (img.dataset.src) { img.src = img.dataset.src; img.removeAttribute('data-src'); } };
  let i = 0;
  load(imgs[1]);
  const step = () => {
    if (document.hidden) return;
    const next = imgs[(i + 1) % imgs.length];
    if (!next.complete || !next.naturalWidth) { load(next); return; }    // wait until it has loaded
    const prev = imgs[i];
    prev.classList.add('is-leaving');            // keep drifting while it fades out...
    prev.classList.remove('is-on');
    setTimeout(() => prev.classList.remove('is-leaving'), 2700);   // ...then reset once invisible (fade: 2.5 s)
    next.classList.remove('is-leaving');
    next.classList.add('is-on');
    i = (i + 1) % imgs.length;
    load(imgs[(i + 1) % imgs.length]);
    if (credit) {
      credit.classList.add('is-out');
      setTimeout(() => {
        credit.href = next.dataset.href;
        credit.lastChild.textContent = ' ' + next.dataset.name;
        credit.classList.remove('is-out');
      }, 600);
    }
  };
  setInterval(step, 8000);
})();
