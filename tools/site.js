// Paper Maximizer: character counter, library filter, search and a copy button.
// The only request is the same-origin search index. No storage, no third parties. The site works without it.
(() => {
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Home: the character count runs up once.
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
      for (const t of document.querySelectorAll('.stack .book, .shelf .tile')) t.hidden = q && !t.textContent.toLowerCase().includes(q);
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
