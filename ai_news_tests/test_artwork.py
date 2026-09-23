import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_news import artwork, build_site

IMAGE = b'RIFF' + b'\x10\x00\x00\x00' + b'WEBPVP8 ' + b'example'
ARTICLE = {'id': 'a' * 24, 'title': 'AI agents learn new tasks', 'summary': 'Research into useful assistants.'}


class ArtworkTests(unittest.TestCase):
    def test_missing_key_blocks_generation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), patch.object(artwork, 'generate') as generate:
            with self.assertRaisesRegex(RuntimeError, 'OPENAI_API_KEY'):
                artwork.ensure_artwork([ARTICLE], tmp)
            generate.assert_not_called()

    def test_image_is_cached_and_not_charged_again(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(artwork, 'generate', return_value=IMAGE) as generate:
            manifest = artwork.ensure_artwork([ARTICLE], tmp)
            self.assertTrue(artwork.has_artwork(ARTICLE['id'], manifest, Path(tmp)))
            with patch.dict(os.environ, {}, clear=True):
                artwork.ensure_artwork([ARTICLE], tmp)
            generate.assert_called_once()
            self.assertEqual(len(json.loads((Path(tmp) / 'prompts.json').read_text())), 1)

    def test_failures_and_batch_limit_leave_pending(self):
        second = dict(ARTICLE, id='b' * 24)
        third = dict(ARTICLE, id='c' * 24)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}), patch.object(artwork, 'generate', side_effect=[RuntimeError('Unavailable'), IMAGE]) as generate:
            manifest = artwork.ensure_artwork([ARTICLE, second, third], tmp, max_images=2)
            self.assertEqual(list(manifest), [second['id']])
            self.assertEqual(generate.call_count, 2)

    def test_api_contract_and_invalid_image(self):
        response = json.dumps({'data': [{'b64_json': base64.b64encode(IMAGE).decode()}]}).encode()
        with patch.object(artwork, 'urlopen', return_value=io.BytesIO(response)) as request:
            self.assertEqual(artwork.generate('Prompt', 'test-only', artwork.MODEL), IMAGE)
            body = json.loads(request.call_args.args[0].data)
            self.assertEqual(body['output_format'], 'webp')
            self.assertEqual(body['n'], 1)
        with patch.object(artwork, 'urlopen', return_value=io.BytesIO(b'{"data":[{"b64_json":"aGVsbG8="}]}')):
            with self.assertRaisesRegex(RuntimeError, 'WebP'):
                artwork.generate('Prompt', 'test-only', artwork.MODEL)

    def test_publication_excludes_pending_articles_but_retains_snapshot(self):
        second = dict(ARTICLE, id='b' * 24)
        snapshot = {'articles': [ARTICLE, second], 'sources': []}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'artwork').mkdir()
            (root / 'artwork' / (ARTICLE['id'] + '.webp')).write_bytes(IMAGE)
            manifest = {ARTICLE['id']: {'url': '/artwork/' + ARTICLE['id'] + '.webp'}}
            path = root / 'snapshot.json'
            path.write_text(json.dumps(snapshot))
            with patch('sys.argv', ['build', '--snapshot', str(path), '--generate-artwork']), patch.object(build_site, 'STATIC', root), patch.object(build_site, 'ensure_artwork', return_value=manifest), patch.object(build_site, 'build') as build:
                build_site.main()
                self.assertEqual(build.call_args.args[0]['articles'], [ARTICLE])
            self.assertEqual(len(json.loads(path.read_text())['articles']), 2)
