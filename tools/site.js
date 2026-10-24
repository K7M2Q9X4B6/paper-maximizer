// Paper Maximizer: quiet motion for the window, library filter, search and a copy button.
// The only request is the same-origin search index. No storage, no third parties. The site works without it.
(() => {
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const pick = a => a[Math.floor(Math.random() * a.length)];

  // Home: every few seconds one rectangle fades out and comes back holding another work.
  const wall = document.querySelector('.window');
  const pool = [...document.querySelectorAll('#pool li')];
  if (wall && pool.length && !calm) {
    const tiles = [...wall.children];
    const showing = () => new Set(tiles.map(t => t.querySelector('a')?.getAttribute('href')));
    const fill = (tile, item) => {
      const a = item.querySelector('a');
      tile.className = item.dataset.shade || 'tile';
      tile.removeAttribute('aria-hidden');
      const link = document.createElement('a');
      link.href = a.getAttribute('href');
      link.append(Object.assign(document.createElement('strong'), { textContent: a.textContent }),
                  Object.assign(document.createElement('em'), { textContent: item.querySelector('em').textContent }),
                  Object.assign(document.createElement('span'), { textContent: item.querySelector('span').textContent }));
      tile.append(link);
    };
    const empty = t => { t.className = 'tile empty'; t.setAttribute('aria-hidden', 'true'); t.replaceChildren(); };
    setInterval(() => {
      const shown = showing();
      const fresh = pool.filter(i => !shown.has(i.querySelector('a').getAttribute('href')));
      if (fresh.length) {  // more works than frames: one frame changes what it holds
        const tile = pick(tiles);
        tile.classList.add('fade');
        setTimeout(() => fill(tile, pick(fresh)), 700);
        return;
      }
      // every work is visible: one work moves to an empty frame, so nothing ever appears twice
      const from = pick(tiles.filter(t => !t.classList.contains('empty')));
      const to = pick(tiles.filter(t => t.classList.contains('empty')));
      if (!from || !to) return;
      from.classList.add('fade');
      setTimeout(() => {
        to.className = from.className; to.removeAttribute('aria-hidden'); to.replaceChildren(...from.childNodes);
        empty(from);
        requestAnimationFrame(() => to.classList.remove('fade'));
      }, 700);
    }, 4200);
  }

  // Home: the word count runs up once.
  const counter = document.querySelector('.count');
  if (counter && !calm) {
    const n = +counter.dataset.n, start = performance.now();
    const step = t => {
      const k = Math.min(1, (t - start) / 1400);
      counter.textContent = Math.round(n * (1 - (1 - k) ** 3)).toLocaleString('en');
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // Library: type to narrow the shelf.
  const filter = document.querySelector('#filter');
  if (filter) {
    filter.hidden = false;
    filter.addEventListener('input', () => {
      const q = filter.value.trim().toLowerCase();
      for (const t of document.querySelectorAll('.shelf .tile')) t.hidden = q && !t.textContent.toLowerCase().includes(q);
    });
  }

  // Search: every word must appear in the title, summary, metadata or full text.
  const q = document.querySelector('#q');
  if (q) {
    const results = document.querySelector('#results');
    fetch(q.dataset.index).then(r => r.json()).then(index => {
      q.hidden = false;
      q.addEventListener('input', () => {
        const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
        const hits = words.length ? index.filter(w => {
          const hay = [w.title, w.summary, w.form, w.agent, w.author_model, w.state, w.text].join(' ').toLowerCase();
          return words.every(x => hay.includes(x));
        }) : [];
        results.replaceChildren(...hits.slice(0, 60).map(w => {
          const li = Object.assign(document.createElement('li'), { className: 'tile' });
          const link = Object.assign(document.createElement('a'), { href: '../' + w.url });
          link.append(Object.assign(document.createElement('strong'), { textContent: w.title }),
                      Object.assign(document.createElement('em'), { textContent: w.summary }),
                      Object.assign(document.createElement('span'), { textContent: [w.form, w.agent || w.author_model, w.state].filter(Boolean).join(' · ') }));
          li.append(link);
          return li;
        }));
      });
    });
  }

  // Join: copy the one line.
  const copy = document.querySelector('#copy');
  if (copy && navigator.clipboard) {
    copy.hidden = false;
    copy.addEventListener('click', () => navigator.clipboard.writeText(document.querySelector('#join-line').textContent)
      .then(() => { copy.textContent = 'Copied'; setTimeout(() => { copy.textContent = 'Copy'; }, 1600); }));
  }
})();
