let articles = [], artwork = {}, topic = '', savedOnly = false;
const staticMode = document.body.dataset.mode === 'static';
const bookmarkKey = 'ai-brief-saved-v1';
function bookmarks() {
  try { const ids = JSON.parse(localStorage.getItem(bookmarkKey) || '[]'); return new Set(Array.isArray(ids) ? ids : []); }
  catch { return new Set(); }
}
const $ = id => document.getElementById(id);
const element = (tag, text, cls) => { const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el; };
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) throw new Error(`Request failed (${response.status}). Please try again.`);
  return response.json();
}
function render() {
  const query = $('search').value.toLowerCase();
  const filtered = articles.filter(a => (!savedOnly || a.saved) && (!topic || a.topic === topic) && (!$('source').value || a.source === $('source').value) && `${a.title} ${a.summary} ${a.source} ${a.topic}`.toLowerCase().includes(query));
  $('count').textContent = articles.length;
  $('saved-count').textContent = articles.filter(a => a.saved).length;
  $('results').textContent = `${filtered.length} ${filtered.length === 1 ? 'story' : 'stories'}`;
  $('heading').textContent = savedOnly ? 'Your reading list' : 'Latest stories';
  $('all').classList.toggle('active', !savedOnly); $('saved').classList.toggle('active', savedOnly);
  $('topics').replaceChildren();
  ['', ...new Set(articles.map(a => a.topic))].forEach(name => {
    const button = element('button', name ? `${name} · ${articles.filter(a => a.topic === name).length}` : 'All topics', topic === name ? 'selected' : '');
    button.onclick = () => { topic = name; render(); }; button.setAttribute('aria-pressed', String(topic === name)); $('topics').append(button);
  });
  $('articles').replaceChildren();
  if (!filtered.length) {
    const empty = element('div', '', 'empty');
    empty.append(element('h3', articles.length ? 'No stories here yet.' : 'Your next briefing starts here.'), element('p', articles.length ? 'Try another filter or save a story to read later.' : 'Click Refresh news to collect the latest AI stories from publisher feeds.'));
    $('articles').append(empty);
  }
  filtered.forEach(a => {
    const card = element('article', '', 'card');
    if (artwork[a.id]) {
      const figure = element('figure', '', 'article-artwork');
      const picture = document.createElement('img');
      picture.src = artwork[a.id].url;
      picture.alt = artwork[a.id].alt;
      picture.loading = 'lazy';
      picture.decoding = 'async';
      picture.width = 1536;
      picture.height = 1024;
      picture.onerror = () => figure.remove();
      figure.append(picture, element('figcaption', 'AI-generated illustration'));
      card.append(figure);
    }
    const meta = element('div', '', 'meta'); meta.append(element('span', a.source), element('span', a.published ? new Date(a.published).toLocaleDateString(undefined, {month:'short',day:'numeric',year:'numeric'}) : 'Date unavailable'));
    const link = element('a', a.title); link.href = a.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    const title = element('h3', ''); title.append(link);
    const bottom = element('div', '', 'card-bottom');
    const save = element('button', a.saved ? '✓ Saved' : '+ Save'); save.setAttribute('aria-label', `${a.saved ? 'Unsave' : 'Save'} ${a.title}`); save.setAttribute('aria-pressed', String(!!a.saved));
    save.onclick = async () => {
      save.disabled = true;
      try {
        if (staticMode) {
          const ids = bookmarks();
          a.saved ? ids.delete(a.id) : ids.add(a.id);
          localStorage.setItem(bookmarkKey, JSON.stringify([...ids]));
        } else { await api('/api/save', {id:a.id, saved:!a.saved}); }
        a.saved = !a.saved; render();
      } catch(e) { $('message').textContent = staticMode ? 'Could not save this story. Allow browser storage and try again.' : e.message; save.disabled=false; }
    };
    bottom.append(element('span', a.topic, 'tag'), save);
    card.append(meta, title, element('p', a.summary, 'summary'), bottom); $('articles').append(card);
  });
}
async function load() {
  const [data, images] = await Promise.all([api(staticMode ? './news.json?t=' + Date.now() : '/api/articles'), api(staticMode ? './artwork.json' : '/api/artwork')]);
  articles = data.articles; artwork = images;
  if (staticMode) {
    const ids = bookmarks();
    articles.forEach(a => { a.saved = ids.has(a.id); });
    $('message').textContent = data.updated ? `Edition updated ${new Date(data.updated).toLocaleString()}. Scheduled every four hours, including 07:00 Dublin time.` : 'Scheduled every four hours, including 07:00 Dublin time.';
  }
  const selected = $('source').value;
  $('source').replaceChildren(new Option('All sources', ''), ...[...new Set(articles.map(a => a.source))].map(s => new Option(s, s))); $('source').value = selected;
  $('source-status').replaceChildren();
  if (!data.sources.length) $('source-status').append(element('p', 'Sources: TechCrunch · The Verge · MIT Technology Review. No feeds checked yet.'));
  data.sources.forEach(s => $('source-status').append(element('p', `${s.error ? '○' : '●'} ${s.source} — ${s.error ? 'Unavailable: ' + s.error : 'Feed checked'} · ${new Date(s.checked).toLocaleString()}`, s.error ? 'source-error' : '')));
  render();
}
$('refresh').onclick = async () => { $('refresh').disabled = true; $('refresh').textContent = 'Checking…'; $('message').textContent = 'Checking for the latest news…'; try { if (!staticMode) await api('/api/refresh', {}); await load(); if (!staticMode) $('message').textContent = 'Refresh complete. See individual feed status below.'; } catch(e) { $('message').textContent = e.message; } finally { $('refresh').disabled = false; $('refresh').textContent = staticMode ? '↻ Reload news' : '↻ Refresh news'; } };
$('all').onclick = () => { savedOnly = false; render(); }; $('saved').onclick = () => { savedOnly = true; render(); };
$('search').oninput = render; $('source').onchange = render;
load().catch(e => { $('message').textContent = e.message; });
