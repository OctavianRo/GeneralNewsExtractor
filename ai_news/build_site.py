"""Collect feeds and export a static GitHub Pages site."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .app import SOURCES, STATIC, fetch_source
from .artwork import ensure_artwork, has_artwork


def collect(previous):
    articles = {a['id']: {k: v for k, v in a.items() if k != 'saved'} for a in previous.get('articles', [])}
    checked = datetime.now(timezone.utc).isoformat()
    statuses = []
    successes = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch_source, SOURCES.items()))
    for source, entries, error in results:
        if not error and not entries:
            error = 'No AI stories returned; previous stories retained'
        statuses.append({'source': source, 'checked': checked, 'error': error})
        if not error:
            successes += 1
            for article in entries:
                articles[article['id']] = article
    if not successes:
        raise RuntimeError('All feeds failed or returned no AI stories; keeping the previously published site')
    ordered = sorted(articles.values(), key=lambda a: (a['published'], a['id']), reverse=True)[:300]
    return {'articles': ordered, 'sources': statuses, 'updated': checked}


def build(snapshot, output):
    output.mkdir(parents=True, exist_ok=True)
    html = (STATIC / 'index.html').read_text()
    html = html.replace('<body>', '<body data-mode="static">')
    html = html.replace('href="/style.css"', 'href="./style.css"').replace('src="/app.js"', 'src="./app.js"').replace('href="/"', 'href="./"')
    html = html.replace('Refresh to check publisher feeds.', 'Feeds refresh every four hours, including 07:00 Europe/Dublin. Reload news checks the latest published edition. Scheduled updates may be delayed by GitHub.')
    html = html.replace('↻ Refresh news', '↻ Reload news')
    (output / 'index.html').write_text(html)
    for filename in ('app.js', 'style.css'):
        shutil.copy2(STATIC / filename, output / filename)
    (output / '.nojekyll').touch()
    # Never export local bookmark state or the database.
    clean = dict(snapshot, articles=[{k: v for k, v in a.items() if k != 'saved'} for a in snapshot['articles']])
    (output / 'news.json').write_text(json.dumps(clean, ensure_ascii=False))
    artwork = json.loads((STATIC / 'artwork' / 'manifest.json').read_text())
    (output / 'artwork').mkdir(exist_ok=True)
    for entry in artwork.values():
        filename = Path(entry['url']).name
        shutil.copy2(STATIC / 'artwork' / filename, output / 'artwork' / filename)
        entry['url'] = './artwork/' + filename
    (output / 'artwork.json').write_text(json.dumps(artwork, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, default=Path('data/news.json'))
    parser.add_argument('--output', type=Path, default=Path('_site'))
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--generate-artwork', action='store_true')
    parser.add_argument('--max-images', type=int, default=12)
    args = parser.parse_args()
    previous = json.loads(args.snapshot.read_text()) if args.snapshot.exists() else {}
    snapshot = collect(previous) if args.refresh else previous
    if not snapshot.get('articles'):
        raise RuntimeError('No news snapshot. Run with --refresh first.')
    if args.max_images < 1:
        parser.error('--max-images must be positive')
    if args.refresh:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    publication = snapshot
    if args.generate_artwork:
        manifest = ensure_artwork(snapshot['articles'], STATIC / 'artwork', args.max_images)
        illustrated = [a for a in snapshot['articles'] if has_artwork(a['id'], manifest, STATIC / 'artwork')]
        pending = len(snapshot['articles']) - len(illustrated)
        print(f'{pending} stories awaiting artwork; held back until illustrated')
        if not illustrated:
            raise RuntimeError('No illustrated stories ready; existing site preserved')
        publication = dict(snapshot, articles=illustrated)
    build(publication, args.output)
    print(f'Built {len(publication["articles"])} stories in {args.output}')


if __name__ == '__main__':
    main()
