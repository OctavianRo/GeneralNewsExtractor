import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from ai_news import app
from ai_news.model import classify, plain_text, summarize

RSS = b'''<rss><channel><item><title>OpenAI releases a reasoning model</title><link>https://example.com/story?utm_source=rss</link><description>&lt;p&gt;An AI research model achieves a new benchmark.&lt;/p&gt;</description><pubDate>Wed, 23 Sep 2026 12:00:00 GMT</pubDate></item><item><title>Football results</title><link>https://example.com/sport</link><description>A game.</description></item><item><title>AI unsafe link</title><link>javascript:alert(1)</link></item></channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI chip funding</title><link href="https://example.com/chips"/><link rel="self" href="https://example.com/api"/><updated>2026-09-23T10:30:00Z</updated><summary>AI chip and GPU semiconductor investment.</summary></entry></feed>'''

class NewsTests(unittest.TestCase):
    def test_rss_filters_and_normalizes(self):
        items = app.parse_feed(RSS, 'Example')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['url'], 'https://example.com/story')
        self.assertEqual(items[0]['topic'], 'Models & research')
        self.assertEqual(items[0]['published'], '2026-09-23T12:00:00+00:00')

    def test_atom_alternate_link(self):
        item = app.parse_feed(ATOM, 'Example')[0]
        self.assertEqual(item['url'], 'https://example.com/chips')
        self.assertEqual(item['topic'], 'Hardware')

    def test_artwork_routes_and_missing_assets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'STATIC', Path(tmp)):
            handler = Mock()
            handler.path = '/api/artwork'
            app.Handler.do_GET(handler)
            handler.reply.assert_called_with(200, {})
            folder = Path(tmp) / 'artwork'
            folder.mkdir()
            (folder / 'manifest.json').write_text('{"test": {"alt": "Illustration"}}')
            app.Handler.do_GET(handler)
            handler.reply.assert_called_with(200, {'test': {'alt': 'Illustration'}})
            article_id = 'a' * 24
            (folder / (article_id + '.png')).write_bytes(b'image bytes')
            handler.path = '/artwork/' + article_id + '.png'
            app.Handler.do_GET(handler)
            handler.reply.assert_called_with(200, b'image bytes', 'image/png')
            handler.path = '/artwork/' + 'b' * 24 + '.png'
            app.Handler.do_GET(handler)
            self.assertEqual(handler.reply.call_args.args[0], 404)
            handler.path = '/artwork/../../README.md'
            app.Handler.do_GET(handler)
            self.assertEqual(handler.reply.call_args.args[0], 404)

    def test_summary_preserves_abbreviations(self):
        text = 'Sen. Smith and Rep. Jones propose AI legislation. It covers safety. More follows.'
        self.assertEqual(summarize(text), 'Sen. Smith and Rep. Jones propose AI legislation. It covers safety.')

    def test_plain_summary(self):
        self.assertEqual(plain_text('<p>Hello</p><script>bad()</script><p>world &amp; AI</p>'), 'Hello world & AI')
        self.assertLessEqual(len(summarize('word ' * 200)), 361)
        self.assertEqual(classify('AI copyright lawsuit', 'regulation policy'), 'Policy & safety')
        self.assertEqual(app.timestamp('not a date'), '')

    def test_refresh_deduplicates_preserves_saved_and_cached_on_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'DB', Path(tmp) / 'news.db'):
            app.initialize()
            item = app.parse_feed(RSS, 'Example')[0]
            with patch.object(app, 'SOURCES', {'Example': 'https://example.com/feed'}), patch.object(app, 'fetch_source', return_value=('Example', [item], None)):
                app.refresh()
                with app.connect() as db:
                    db.execute('UPDATE articles SET saved=1')
                app.refresh()
            with patch.object(app, 'SOURCES', {'Example': 'https://example.com/feed'}), patch.object(app, 'fetch_source', return_value=('Example', [], 'Timed out')):
                app.refresh()
            with app.connect() as db:
                rows = db.execute('SELECT * FROM articles').fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['saved'], 1)
                self.assertEqual(db.execute('SELECT error FROM source_status').fetchone()[0], 'Timed out')

if __name__ == '__main__':
    unittest.main()
