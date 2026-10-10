# Part of ci_ai.

from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiProviderConfig(CiAiTransactionCase):

    def setUp(self):
        super().setUp()
        # DB may retain admin Settings from manual testing; start each case clean.
        self.env['ci.ai.provider.config'].get_solo().write({
            'name': 'AI Providers',
            'chat_provider': 'iap',
            'embedding_provider': 'iap',
            'stt_provider': 'iap',
            'image_provider': 'iap',
            'anthropic_enabled': False,
            'openai_enabled': False,
            'google_enabled': False,
            'anthropic_api_key': False,
            'openai_api_key': False,
            'google_api_key': False,
            'anthropic_model': 'claude-sonnet-4-20250514',
            'anthropic_base_url': 'https://api.anthropic.com',
            'openai_gateway': 'openai',
            'openai_model': 'gpt-4o',
            'openai_embedding_model': 'text-embedding-3-small',
            'openai_stt_model': 'whisper-1',
            'openai_realtime_stt_model': 'gpt-live-transcribe',
            'openai_image_model': 'dall-e-3',
            'openai_base_url': 'https://api.openai.com',
            'google_model': 'gemini-2.5-flash',
            'google_embedding_model': 'gemini-embedding-001',
            'google_stt_model': 'gemini-2.5-flash',
            'google_image_model': 'gemini-2.5-flash-image',
            'google_base_url': 'https://generativelanguage.googleapis.com',
        })

    def test_singleton_get_solo(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertTrue(config)
        self.assertEqual(config.chat_provider, 'iap')
        self.assertEqual(config.name, 'AI Providers')

    def test_anthropic_requires_enable_and_key(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'anthropic',
                'anthropic_enabled': False,
                'anthropic_api_key': 'sk-test',
            })
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'anthropic',
                'anthropic_enabled': True,
                'anthropic_api_key': '',
            })

    def test_openai_requires_enable_and_key(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'openai',
                'openai_enabled': False,
                'openai_api_key': 'sk-test',
            })
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'openai',
                'openai_enabled': True,
                'openai_api_key': '',
            })

    def test_openai_embedding_requires_enable_and_key(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'embedding_provider': 'openai',
                'openai_enabled': False,
                'openai_api_key': 'sk-test',
            })
        with self.assertRaises(ValidationError):
            config.write({
                'embedding_provider': 'openai',
                'openai_enabled': True,
                'openai_api_key': '',
            })

    def test_google_requires_enable_and_key(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'google',
                'google_enabled': False,
                'google_api_key': 'AIza-test',
            })
        with self.assertRaises(ValidationError):
            config.write({
                'chat_provider': 'google',
                'google_enabled': True,
                'google_api_key': '',
            })

    def test_google_embedding_requires_enable_and_key(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'embedding_provider': 'google',
                'google_enabled': False,
                'google_api_key': 'AIza-test',
            })
        with self.assertRaises(ValidationError):
            config.write({
                'embedding_provider': 'google',
                'google_enabled': True,
                'google_api_key': '',
            })

    def test_settings_ai_app_fields(self):
        values = self.env['res.config.settings'].get_values()
        self.assertEqual(values.get('ci_ai_chat_provider'), 'iap')
        settings = self.env['res.config.settings'].create({
            'ci_ai_anthropic_enabled': True,
            'ci_ai_anthropic_api_key': 'sk-anthropic',
            'ci_ai_chat_provider': 'anthropic',
        })
        settings.execute()
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertTrue(config.anthropic_enabled)
        self.assertEqual(config.chat_provider, 'anthropic')
        self.assertEqual(config.anthropic_api_key, 'sk-anthropic')

    def test_settings_openai_fields(self):
        settings = self.env['res.config.settings'].create({
            'ci_ai_openai_enabled': True,
            'ci_ai_openai_gateway': 'openai',
            'ci_ai_openai_api_key': 'sk-openai',
            'ci_ai_openai_model': 'gpt-test',
            'ci_ai_openai_embedding_model': 'text-embedding-3-large',
            'ci_ai_chat_provider': 'openai',
            'ci_ai_embedding_provider': 'openai',
        })
        settings.execute()
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertTrue(config.openai_enabled)
        self.assertEqual(config.openai_gateway, 'openai')
        self.assertEqual(config.chat_provider, 'openai')
        self.assertEqual(config.embedding_provider, 'openai')
        self.assertEqual(config.openai_api_key, 'sk-openai')
        self.assertEqual(config.openai_model, 'gpt-test')
        self.assertEqual(config.openai_embedding_model, 'text-embedding-3-large')

    def test_deepseek_gateway_rejects_openai_embeddings(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'openai_enabled': True,
                'openai_api_key': 'sk-deepseek',
                'openai_gateway': 'deepseek',
                'chat_provider': 'openai',
                'embedding_provider': 'openai',
            })

    def test_deepseek_gateway_allows_chat_only(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'openai_enabled': True,
            'openai_api_key': 'sk-deepseek',
            'openai_gateway': 'deepseek',
            'openai_model': 'deepseek-chat',
            'chat_provider': 'openai',
            'embedding_provider': 'iap',
            'stt_provider': 'iap',
            'image_provider': 'iap',
        })
        self.assertEqual(config.openai_gateway, 'deepseek')
        self.assertEqual(config.chat_provider, 'openai')

    def test_settings_google_fields(self):
        settings = self.env['res.config.settings'].create({
            'ci_ai_google_enabled': True,
            'ci_ai_google_api_key': 'AIza-google',
            'ci_ai_google_model': 'gemini-test',
            'ci_ai_google_embedding_model': 'gemini-embedding-001',
            'ci_ai_chat_provider': 'google',
            'ci_ai_embedding_provider': 'google',
        })
        settings.execute()
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertTrue(config.google_enabled)
        self.assertEqual(config.chat_provider, 'google')
        self.assertEqual(config.embedding_provider, 'google')
        self.assertEqual(config.google_api_key, 'AIza-google')
        self.assertEqual(config.google_model, 'gemini-test')
        self.assertEqual(config.google_embedding_model, 'gemini-embedding-001')

    def test_non_system_cannot_write(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        user = self.env['res.users'].create({
            'name': 'Internal CI AI',
            'login': 'ci_ai_internal',
            'group_ids': [Command.set(self.env.ref('base.group_user').ids)],
        })
        with self.assertRaises(AccessError):
            config.with_user(user).write({'anthropic_model': 'x'})
