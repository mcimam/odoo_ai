# Part of ci_ai.

from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.ci_ai.providers.google_provider import GoogleEmbeddingProvider
from odoo.addons.ci_ai.providers.openai_provider import OpenAIEmbeddingProvider
from odoo.addons.ci_ai.providers.router import (
    get_embedding_provider,
    get_embedding_provider_name,
)
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiEmbeddings(CiAiTransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ci.ai.provider.config'].get_solo().write({
            'chat_provider': 'iap',
            'embedding_provider': 'iap',
            'openai_enabled': False,
            'openai_api_key': False,
            'openai_embedding_model': 'text-embedding-3-small',
            'google_enabled': False,
            'google_api_key': False,
            'google_embedding_model': 'gemini-embedding-001',
        })

    def test_router_iap_returns_none(self):
        self.assertEqual(get_embedding_provider_name(self.env), 'iap')
        self.assertIsNone(get_embedding_provider(self.env))

    def test_router_openai(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
            'openai_embedding_model': 'text-embedding-3-small',
        })
        provider = get_embedding_provider(self.env)
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider.model, 'text-embedding-3-small')

    def test_openai_embed_maps_vectors(self):
        provider = OpenAIEmbeddingProvider(api_key='sk-test', model='text-embedding-3-small')
        vector = [0.01] * 1536

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn('/v1/embeddings', url)
            self.assertEqual(body['model'], 'text-embedding-3-small')
            self.assertEqual(body['dimensions'], 1536)
            self.assertEqual(body['input'], ['Title\n\nChunk text', 'query only'])
            return {
                'data': [
                    {'index': 1, 'embedding': vector},
                    {'index': 0, 'embedding': vector},
                ],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.embed(
                inputs=[
                    {'title': 'Title', 'content': 'Chunk text'},
                    {'content': 'query only'},
                ],
                model='text-embedding-3-small',
                mode='document',
            )
        self.assertEqual(len(result['embeddings']), 2)
        self.assertEqual(len(result['embeddings'][0]), 1536)

    def test_get_embeddings_openai_skips_iap(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        vector = [0.2] * 1536
        with patch(
            'odoo.addons.ai.models.ai_embedding.call_odoo_ai',
            side_effect=AssertionError('IAP should not be called'),
        ), patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            return_value={'data': [{'index': 0, 'embedding': vector}]},
        ):
            result = self.env['ai.embedding']._get_embeddings(
                input=[{'content': 'hello'}],
                model='text-embedding-3-small',
                mode='query',
            )
        self.assertEqual(result['embeddings'][0], vector)

    def test_get_embeddings_iap_uses_super(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({'embedding_provider': 'iap'})
        sentinel = {'embeddings': [[0.1] * 1536]}
        with patch(
            'odoo.addons.ai.models.ai_embedding.call_odoo_ai',
            return_value=sentinel,
        ) as mock_iap:
            result = self.env['ai.embedding']._get_embeddings(
                input=[{'content': 'hello'}],
                model='iap-model',
                mode='query',
            )
        mock_iap.assert_called_once()
        self.assertEqual(result, sentinel)

    def test_default_embedding_model_openai(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
            'openai_embedding_model': 'text-embedding-3-large',
        })
        self.assertEqual(
            self.env['ai.embedding']._get_default_embedding_model(),
            'text-embedding-3-large',
        )
        supported = self.env['ai.embedding']._get_supported_embedding_models()
        self.assertIn('text-embedding-3-large', supported)
        self.assertIn('text-embedding-3-small', supported)

    def test_router_google(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
            'google_embedding_model': 'gemini-embedding-001',
        })
        provider = get_embedding_provider(self.env)
        self.assertIsInstance(provider, GoogleEmbeddingProvider)
        self.assertEqual(provider.model, 'gemini-embedding-001')

    def test_google_embed_maps_vectors(self):
        provider = GoogleEmbeddingProvider(api_key='AIza-test', model='gemini-embedding-001')
        vector = [0.01] * 1536

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn(':batchEmbedContents', url)
            self.assertEqual(body['requests'][0]['outputDimensionality'], 1536)
            self.assertEqual(
                body['requests'][0]['content']['parts'][0]['text'],
                'Title\n\nChunk text',
            )
            return {
                'embeddings': [
                    {'values': vector},
                    {'values': vector},
                ],
            }

        with patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.embed(
                inputs=[
                    {'title': 'Title', 'content': 'Chunk text'},
                    {'content': 'query only'},
                ],
                model='gemini-embedding-001',
                mode='document',
            )
        self.assertEqual(len(result['embeddings']), 2)
        self.assertEqual(len(result['embeddings'][0]), 1536)

    def test_get_embeddings_google_skips_iap(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
        })
        vector = [0.2] * 1536
        with patch(
            'odoo.addons.ai.models.ai_embedding.call_odoo_ai',
            side_effect=AssertionError('IAP should not be called'),
        ), patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            return_value={'embedding': {'values': vector}},
        ):
            result = self.env['ai.embedding']._get_embeddings(
                input=[{'content': 'hello'}],
                model='gemini-embedding-001',
                mode='query',
            )
        self.assertEqual(result['embeddings'][0], vector)

    def test_default_embedding_model_google(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'embedding_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
            'google_embedding_model': 'gemini-embedding-001',
        })
        self.assertEqual(
            self.env['ai.embedding']._get_default_embedding_model(),
            'gemini-embedding-001',
        )
        supported = self.env['ai.embedding']._get_supported_embedding_models()
        self.assertIn('gemini-embedding-001', supported)
