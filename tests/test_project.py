import base64
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from evidencedesk.api import create_app
from evidencedesk.config import ROOT, Settings
from evidencedesk.ingest import Chunk, chunk_document
from evidencedesk.pipeline import Service
from evidencedesk.providers import GenerationError, estimate_cost, generate
from evidencedesk.retrieval import Retriever


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / 'documents', self.root / 'documents')
        self.settings = Settings(documents=self.root / 'documents', database=self.root / 'metrics.db',
                                 provider='extractive', vector_backend='tfidf', reranker='coverage')
        self.service = Service(self.settings)

    def tearDown(self):
        self.temporary.cleanup()

    def test_search_and_abstention(self):
        answer = self.service.ask('How do I book a workshop?')
        self.assertEqual(answer['status'], 'evidence')
        self.assertEqual(answer['sources'][0]['source'], '02_workshops.md')
        self.assertEqual(self.service.ask('What will the weather be tomorrow?')['status'], 'abstained')
        self.assertEqual(self.service.telemetry.summary()['requests'], 2)

    def test_chunk_overlap_preserves_tail(self):
        text = ' '.join(f'word{i}' for i in range(251)).encode()
        chunks = chunk_document('long.txt', text, size=100, overlap=20)
        self.assertEqual(chunks[0].text.split()[-20:], chunks[1].text.split()[:20])
        self.assertIn('word250', chunks[-1].text)
        self.assertEqual(len(chunks), 3)

    def test_repeated_upload_and_restart(self):
        encoded = base64.b64encode(b'Zebras require a striped access badge for admission.').decode()
        first = self.service.upload('../../escape.txt', encoded)
        second = self.service.upload('../../escape.txt', encoded)
        self.assertTrue(second['deduplicated'])
        self.assertFalse((self.root / 'escape.txt').exists())
        self.assertEqual(Service(self.settings).index.fingerprint, first['index_version'])
        self.assertEqual(self.service.ask('What access badge do zebras require?')['status'], 'evidence')

    def test_failed_index_build_is_atomic(self):
        before = self.service.index.fingerprint
        with patch('evidencedesk.pipeline.Retriever', side_effect=RuntimeError('model unavailable')):
            with self.assertRaises(RuntimeError):
                self.service.upload('new.txt', base64.b64encode(b'Interesting new material.').decode())
        self.assertEqual(before, self.service.index.fingerprint)
        self.assertEqual(list(self.settings.documents.glob('user_*')), [])

    def test_parallel_duplicate_uploads(self):
        encoded = base64.b64encode(b'The special approval code is sapphire.').decode()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: self.service.upload('new.txt', encoded), range(3)))
        self.assertEqual(sum(not r['deduplicated'] for r in results), 1)
        self.assertEqual(len(list(self.settings.documents.glob('user_*'))), 1)

    def test_empty_index_and_stop_words(self):
        empty = Retriever([], self.settings)
        self.assertEqual(empty.search('workshop'), [])
        stop = Retriever([Chunk('abc', 'stop.txt', 1, 'the and or')], self.settings)
        self.assertEqual(stop.search('the and'), [])

    def test_api_workflow_and_validation(self):
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/api/health').json()['chunks'], 12)
            self.assertEqual(client.post('/api/ask', json={'question': '   '}).status_code, 422)
            self.assertEqual(client.post('/api/ask', json={'question': 'booking', 'mode': 'bad'}).status_code, 422)
            result = client.post('/api/ask', json={'question': 'How do I book a workshop?'}).json()
            self.assertEqual(result['status'], 'evidence')
            self.assertEqual(client.get('/api/metrics').json()['requests'], 1)
            self.assertEqual(client.post('/api/evaluate', json={}).json()['question_count'], 60)
            self.assertFalse(client.get('/api/evaluation').json()['stale'])
            upload = {'filename': 'new.txt', 'content_base64': base64.b64encode(b'A new astronomy document.').decode()}
            self.assertEqual(client.post('/api/documents', json=upload).status_code, 200)
            self.assertTrue(client.get('/api/evaluation').json()['stale'])

    def test_bad_files_and_cross_origin(self):
        with TestClient(create_app(self.settings)) as client:
            for filename, content in [('bad.pdf', b'broken'), ('blank.txt', b''), ('script.html', b'<script>')]:
                response = client.post('/api/documents', json={'filename': filename, 'content_base64': base64.b64encode(content).decode()})
                self.assertEqual(response.status_code, 400)
            self.assertEqual(client.post('/api/ask', json={'question': 'workshop'}, headers={'Origin': 'https://example.org'}).status_code, 403)

    def test_document_preview_uses_indexed_content_only(self):
        with TestClient(create_app(self.settings)) as client:
            preview = client.get('/api/documents/02_workshops.md')
            self.assertEqual(preview.status_code, 200)
            chunks = preview.json()['chunks']
            self.assertIn('programme desk', chunks[0]['text'])
            self.assertTrue(all(chunk['source'] == '02_workshops.md' for chunk in chunks))
            for source in ['missing.txt', '.env', '..%2F.env']:
                self.assertEqual(client.get('/api/documents/' + source).status_code, 404)
            uploaded = client.post('/api/documents', json={
                'filename': 'notes.txt',
                'content_base64': base64.b64encode(b'The observatory opens at dusk.').decode()
            }).json()
            filename = next(name for name in uploaded['documents'] if name.startswith('user_'))
            self.assertIn('observatory', client.get('/api/documents/' + filename).json()['chunks'][0]['text'])

    def test_blank_and_encrypted_pdfs(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        raw = BytesIO()
        writer.write(raw)
        with self.assertRaisesRegex(ValueError, 'No readable text'):
            chunk_document('blank.pdf', raw.getvalue())
        writer.encrypt('password')
        raw = BytesIO()
        writer.write(raw)
        with self.assertRaisesRegex(ValueError, 'password protection'):
            chunk_document('locked.pdf', raw.getvalue())

    def test_text_pdf_preserves_page_number(self):
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 10 100 Td (Workshop bookings open weekly.) Tj ET')
        page[NameObject('/Contents')] = stream
        raw = BytesIO()
        writer.write(raw)
        chunks = chunk_document('report.pdf', raw.getvalue())
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].page, 2)
        self.assertIn('Workshop bookings open weekly', chunks[0].text)

    def test_provider_exact_citation_and_usage(self):
        hits = self.service.index.search('How do I book a workshop?')
        claim = {'text': 'Book through the programme desk.', 'source_id': hits[0]['id'], 'quote': 'programme desk'}
        payload = {'message': {'content': json.dumps({'answerable': True, 'claims': [claim]})}, 'prompt_eval_count': 100, 'eval_count': 25}
        settings = replace(self.settings, provider='ollama')
        with patch('evidencedesk.providers.httpx.Client') as mock:
            mock.return_value.__enter__.return_value.post.return_value = httpx.Response(200, json=payload, request=httpx.Request('POST', 'http://localhost'))
            answer, usage = generate('How do I book?', hits, settings)
            self.assertTrue(answer.answerable)
            self.assertEqual(usage['input_tokens'], 100)
            claim['source_id'] = 'fabricated'
            payload['message']['content'] = json.dumps({'answerable': True, 'claims': [claim]})
            mock.return_value.__enter__.return_value.post.return_value = httpx.Response(200, json=payload, request=httpx.Request('POST', 'http://localhost'))
            with self.assertRaises(GenerationError):
                generate('How do I book?', hits, settings)

    def test_cloud_protocol_and_unknown_cost_after_retry(self):
        settings = replace(self.settings, provider='openai-compatible', api_key='test', model='test', input_price='1', output_price='2')
        body = {'choices': [{'message': {'content': json.dumps({'answerable': False, 'claims': []})}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
        response = httpx.Response(200, json=body, request=httpx.Request('POST', 'https://example.org'))
        with patch('evidencedesk.providers.httpx.Client') as mock, patch('evidencedesk.providers.time.sleep'):
            post = mock.return_value.__enter__.return_value.post
            post.side_effect = [httpx.ConnectError('offline'), response]
            answer, usage = generate('Test?', [], settings)
            self.assertFalse(answer.answerable)
            self.assertEqual(usage['attempts'], 2)
            self.assertIsNone(estimate_cost(settings, usage))
        self.assertAlmostEqual(estimate_cost(settings, {'attempts': 1, 'input_tokens': 100, 'output_tokens': 20}), 0.00014)

    def test_provider_failure_logged(self):
        service = Service(replace(self.settings, provider='ollama'))
        with patch('evidencedesk.pipeline.generate', side_effect=GenerationError('Connection failed')):
            result = service.ask('How do I book a workshop?')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(service.telemetry.summary()['error_rate'], 1)

    def test_semantic_and_cross_encoder_contracts(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        encoder = MagicMock()
        encoder.encode.return_value = np.array([[1.0, 0.0]])
        reranker = MagicMock()
        reranker.predict.return_value = np.array([2.0])
        module = SimpleNamespace(SentenceTransformer=MagicMock(return_value=encoder), CrossEncoder=MagicMock(return_value=reranker))
        with patch.dict('sys.modules', {'sentence_transformers': module}):
            retriever = Retriever([Chunk('x', 'x.txt', 1, 'Book a workshop')], replace(self.settings, vector_backend='sentence-transformers', reranker='cross-encoder'))
            hits = retriever.search('Book workshop')
        self.assertEqual(hits[0]['rerank_score'], 2)
        self.assertEqual(hits[0]['similarity'], 1)

    def test_telemetry_excludes_documents_and_prompts(self):
        self.service.ask('How do I book a workshop?')
        with self.service.telemetry.connect() as db:
            raw = db.execute('SELECT payload FROM requests').fetchone()[0]
        self.assertNotIn('How do I', raw)
        self.assertNotIn('programme desk', raw)
        self.assertNotIn('api_key', raw)


if __name__ == '__main__':
    unittest.main()
