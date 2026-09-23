"""Run with python -m ai_news.app. Local, single-user application."""
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .model import AI, classify, plain_text, summarize

SOURCES = {
    'TechCrunch': 'https://techcrunch.com/category/artificial-intelligence/feed/',
    'The Verge': 'https://www.theverge.com/rss/ai-artificial-intelligence/index.xml',
    'MIT Technology Review': 'https://www.technologyreview.com/topic/artificial-intelligence/feed/',
}
STATIC = Path(__file__).parent / 'static'
DB = Path('ai_news.sqlite3')
REFRESH_LOCK = threading.Lock()

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS articles (id TEXT PRIMARY KEY, title TEXT, url TEXT UNIQUE, source TEXT, published TEXT, topic TEXT, summary TEXT, saved INTEGER DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS source_status (source TEXT PRIMARY KEY, checked TEXT, error TEXT)')

def canonical(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith('utm_') and k not in ('fbclid', 'gclid')]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', urlencode(query), ''))

def timestamp(raw):
    try:
        dt = parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return ''
    return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()

def parse_feed(data, source):
    root = ET.fromstring(data)
    articles = []
    for entry in root.iter():
        if entry.tag.split('}')[-1] not in ('item', 'entry'):
            continue
        fields = {}
        link = ''
        for child in entry:
            name = child.tag.split('}')[-1]
            fields[name] = ''.join(child.itertext()).strip()
            if name == 'link' and child.get('rel', 'alternate') == 'alternate':
                link = child.get('href') or fields[name]
        url = canonical(link)
        title = plain_text(fields.get('title', ''))
        html = fields.get('encoded') or fields.get('content') or fields.get('description') or fields.get('summary', '')
        content = plain_text(html)
        # GNE extracts the main text of longer HTML feed bodies when available.
        if len(content) > 600 and '<' in html:
            try:
                from gne import GeneralNewsExtractor
                content = GeneralNewsExtractor().extract('<html><body>' + html + '</body></html>')['content']
            except Exception:
                pass  # Feed excerpts remain usable if main-body extraction fails.
        if not url or not title or not AI.search(title + ' ' + content):
            continue
        articles.append(dict(id=sha256(url.encode()).hexdigest()[:24], title=title, url=url,
                             source=source, published=timestamp(fields.get('pubDate') or fields.get('published') or fields.get('updated', '')),
                             topic=classify(title, content), summary=summarize(content) or 'No excerpt provided. Read the original article for details.'))
    return articles

def fetch_source(item):
    source, url = item
    try:
        request = Request(url, headers={'User-Agent': 'AINewsReader/1.0 (personal RSS reader)'})
        with urlopen(request, timeout=15) as response:
            data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError('Feed exceeds size limit')
        return source, parse_feed(data, source), None
    except Exception as error:
        return source, [], str(error)[:200]

def refresh():
    if not REFRESH_LOCK.acquire(blocking=False):
        return False
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(fetch_source, SOURCES.items()))
        with connect() as db:
            for source, articles, error in results:
                db.execute('INSERT OR REPLACE INTO source_status VALUES (?, ?, ?)', (source, datetime.now(timezone.utc).isoformat(), error))
                for article in articles:
                    db.execute('''INSERT INTO articles (id,title,url,source,published,topic,summary)
                        VALUES (:id,:title,:url,:source,:published,:topic,:summary)
                        ON CONFLICT(id) DO UPDATE SET title=excluded.title, summary=excluded.summary, topic=excluded.topic, published=excluded.published''', article)
        return True
    finally:
        REFRESH_LOCK.release()

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, value, content_type='application/json'):
        data = json.dumps(value).encode() if content_type == 'application/json' else value
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/articles':
            with connect() as db:
                articles = [dict(row) for row in db.execute('SELECT * FROM articles ORDER BY published DESC, title')]
                status = [dict(row) for row in db.execute('SELECT * FROM source_status ORDER BY source')]
            self.reply(200, {'articles': articles, 'sources': status})
        elif path == '/api/artwork':
            manifest = STATIC / 'artwork' / 'manifest.json'
            self.reply(200, json.loads(manifest.read_text()) if manifest.exists() else {})
        elif re.fullmatch(r'/artwork/[a-f0-9]{24}\.png', path):
            asset = STATIC / 'artwork' / path.rsplit('/', 1)[-1]
            if asset.is_file():
                self.reply(200, asset.read_bytes(), 'image/png')
            else:
                self.reply(404, {'error': 'Artwork not found'})
        elif path in ('/', '/app.js', '/style.css'):
            filename, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[path]
            self.reply(200, (STATIC / filename).read_bytes(), mime)
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        # JSON-only requests and same-origin checks protect this local service.
        origin = self.headers.get('Origin')
        if (origin and origin != 'http://' + self.headers.get('Host', '')) or self.headers.get('Content-Type') != 'application/json':
            return self.reply(403, {'error': 'Same-origin JSON request required'})
        if self.path == '/api/refresh':
            return self.reply(200 if refresh() else 409, {'message': 'Refresh finished or already running'})
        if self.path == '/api/save':
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 1024:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get('id'), str) or type(data.get('saved')) is not bool:
                    raise ValueError()
                with connect() as db:
                    cursor = db.execute('UPDATE articles SET saved=? WHERE id=?', (int(data['saved']), data['id']))
                return self.reply(200 if cursor.rowcount else 404, {'ok': bool(cursor.rowcount)})
            except (ValueError, TypeError):
                return self.reply(400, {'error': 'Invalid save request'})
        self.reply(404, {'error': 'Not found'})

def main():
    global DB
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--db', type=Path, default=DB)
    args = parser.parse_args()
    DB = args.db
    initialize()
    print(f'AI Brief is running at http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()
