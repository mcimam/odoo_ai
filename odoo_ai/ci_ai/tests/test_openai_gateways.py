# Part of ci_ai.

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.ci_ai.providers.http_security import (
    is_allowed_openai_host,
    validate_https_base_url,
)
from odoo.addons.ci_ai.providers.openai_gateways import (
    gateway_supports,
    resolve_gateway_base_url,
)
from odoo.addons.ci_ai.providers.openai_provider import (
    OpenAIChatProvider,
    OpenAIEmbeddingProvider,
)
from odoo.addons.ci_ai.providers.router import get_chat_provider
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiOpenAIGateways(CiAiTransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ci.ai.provider.config'].get_solo().write({
            'chat_provider': 'iap',
            'embedding_provider': 'iap',
            'stt_provider': 'iap',
            'image_provider': 'iap',
            'openai_enabled': False,
            'openai_api_key': False,
            'openai_gateway': 'openai',
            'openai_model': 'gpt-4o',
            'openai_base_url': 'https://api.openai.com',
        })

    def test_allowed_compat_hosts(self):
        self.assertTrue(is_allowed_openai_host('api.deepseek.com'))
        self.assertTrue(is_allowed_openai_host('api.groq.com'))
        self.assertTrue(is_allowed_openai_host('openrouter.ai'))
        self.assertFalse(is_allowed_openai_host('evil.example.com'))

    def test_gateway_capabilities(self):
        self.assertTrue(gateway_supports('openai', 'chat'))
        self.assertTrue(gateway_supports('openai', 'embedding'))
        self.assertTrue(gateway_supports('deepseek', 'chat'))
        self.assertFalse(gateway_supports('deepseek', 'embedding'))
        self.assertTrue(gateway_supports('ollama', 'embedding'))
        self.assertFalse(gateway_supports('ollama', 'stt'))

    def test_resolve_named_preset_ignores_stale_base_url(self):
        url = resolve_gateway_base_url('deepseek', 'https://api.openai.com')
        self.assertEqual(url, 'https://api.deepseek.com')

    @patch('odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips', return_value=True)
    def test_validate_groq_path_base_url(self, _mock_dns):
        url = validate_https_base_url(
            'https://api.groq.com/openai',
            default_url='https://api.groq.com/openai',
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
            allow_path=True,
        )
        self.assertEqual(url, 'https://api.groq.com/openai')

    @patch('odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips', return_value=True)
    def test_validate_openrouter_path_base_url(self, _mock_dns):
        url = validate_https_base_url(
            'https://openrouter.ai/api',
            default_url='https://openrouter.ai/api',
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
            allow_path=True,
        )
        self.assertEqual(url, 'https://openrouter.ai/api')

    def test_validate_ollama_loopback_http(self):
        url = validate_https_base_url(
            'http://127.0.0.1:11434',
            default_url='http://127.0.0.1:11434',
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
            allow_loopback=True,
        )
        self.assertEqual(url, 'http://127.0.0.1:11434')

    def test_config_accepts_deepseek_gateway(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-ds',
            'openai_gateway': 'deepseek',
            'chat_provider': 'openai',
        })
        self.assertEqual(config.openai_gateway, 'deepseek')

    def test_config_rejects_evil_custom_host(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'openai_gateway': 'custom',
                'openai_base_url': 'https://evil.example.com',
            })

    def test_router_deepseek_chat_url(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-ds',
            'openai_gateway': 'deepseek',
            'openai_model': 'deepseek-chat',
            'chat_provider': 'openai',
        })
        provider = get_chat_provider(self.env)
        self.assertIsInstance(provider, OpenAIChatProvider)
        self.assertEqual(provider.gateway, 'deepseek')
        self.assertEqual(provider.base_url, 'https://api.deepseek.com')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertEqual(url, 'https://api.deepseek.com/v1/chat/completions')
            self.assertEqual(body['model'], 'deepseek-chat')
            return {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'hello from deepseek'},
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='',
            )
        self.assertIn('hello from deepseek', result['result']['content'][0]['text'])

    def test_router_groq_chat_url(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-groq',
            'openai_gateway': 'groq',
            'openai_model': 'llama-3.3-70b-versatile',
            'chat_provider': 'openai',
            'embedding_provider': 'iap',
            'stt_provider': 'iap',
            'image_provider': 'iap',
        })
        provider = get_chat_provider(self.env)
        self.assertEqual(provider.base_url, 'https://api.groq.com/openai')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertEqual(url, 'https://api.groq.com/openai/v1/chat/completions')
            return {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'hello from groq'},
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='',
            )
        self.assertIn('hello from groq', result['result']['content'][0]['text'])

    def test_embedding_provider_rejects_chat_only_gateway(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-ds',
            'openai_gateway': 'deepseek',
            'chat_provider': 'openai',
            'embedding_provider': 'iap',
        })
        # Bypass config constraint by constructing provider directly.
        provider = OpenAIEmbeddingProvider(
            api_key='sk-ds',
            gateway='deepseek',
            base_url='https://api.deepseek.com',
        )
        with self.assertRaises(UserError):
            provider.embed(['hello'])

    def test_router_embedding_rejects_deepseek_at_runtime(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        # Force an inconsistent state via SQL-free path: write chat-only gateway
        # with embeddings still on iap, then call get_embedding_provider after
        # temporarily flipping embedding_provider without re-validating gateway
        # through a direct ORM write that would fail — use sudo create path.
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-ds',
            'openai_gateway': 'openai',
            'embedding_provider': 'openai',
            'chat_provider': 'openai',
        })
        # Switch gateway after embedding already set — must raise on write.
        with self.assertRaises(ValidationError):
            config.write({'openai_gateway': 'deepseek'})
