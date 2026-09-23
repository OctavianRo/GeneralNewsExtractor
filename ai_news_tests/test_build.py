import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_news import build_site


class BuildTests(unittest.TestCase):
    def test_partial_failure_keeps_old_stories(self):
        old = {'id': 'old', 'published': '2026-09-22', 'saved': 1}
        new = {'id': 'new', 'published': '2026-09-23'}
        with patch.object(build_site, 'SOURCES', {'A': 'a', 'B': 'b'}), patch.object(build_site, 'fetch_source', side_effect=lambda item: ('A', [new], None) if item[0] == 'A' else ('B', [], 'Timeout')):
            result = build_site.collect({'articles': [old]})
        self.assertEqual([a['id'] for a in result['articles']], ['new', 'old'])
        self.assertNotIn('saved', result['articles'][1])
        self.assertEqual(result['sources'][1]['error'], 'Timeout')

    def test_all_failures_prevent_publish(self):
        with patch.object(build_site, 'SOURCES', {'A': 'a'}), patch.object(build_site, 'fetch_source', return_value=('A', [], 'Timeout')):
            with self.assertRaises(RuntimeError):
                build_site.collect({'articles': []})

    def test_static_export_has_relative_paths_and_no_bookmarks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static = root / 'static'
            (static / 'artwork').mkdir(parents=True)
            (static / 'index.html').write_text('<body><a href="/"></a><link href="/style.css"><script src="/app.js"></script></body>')
            (static / 'app.js').write_text('')
            (static / 'style.css').write_text('')
            (static / 'artwork' / 'example.png').write_bytes(b'test')
            (static / 'artwork' / 'manifest.json').write_text('{"id":{"url":"/artwork/example.png","alt":"Example"}}')
            with patch.object(build_site, 'STATIC', static):
                build_site.build({'articles': [{'id': 'id', 'saved': 1}], 'sources': []}, root / 'out')
            html = (root / 'out/index.html').read_text()
            self.assertIn('data-mode="static"', html)
            self.assertNotIn('href="/', html)
            self.assertNotIn('src="/', html)
            self.assertNotIn('saved', json.loads((root / 'out/news.json').read_text())['articles'][0])
            artwork = json.loads((root / 'out/artwork.json').read_text())
            self.assertEqual(artwork['id']['url'], './artwork/example.png')
            self.assertTrue((root / 'out/.nojekyll').exists())
