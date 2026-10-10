# Part of ci_ai.

from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.misc import Callbacks


@tagged('post_install', '-at_install')
class TestCiAiSessionOverride(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({
            'name': 'CI AI Test Agent',
            'system_prompt': 'Test',
        })
        # ai_agent_id is NO_ACCESS for normal writes
        cls.channel = cls.env['discuss.channel'].sudo().create({
            'name': 'CI AI chat',
            'channel_type': 'ai_chat',
            'ai_agent_id': cls.agent.id,
        })
        cls.session = cls.env['ai.session'].sudo().create({
            'agent_id': cls.agent.id,
            'channel_id': cls.channel.id,
        })
        cls.AiSession = cls.registry['ai.session']

    def test_get_completions_iap_calls_iap(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'iap',
            'anthropic_enabled': False,
        })
        sentinel = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'iap'}],
                'provider_metadata': {},
            }
        }
        with patch(
            'odoo.addons.ai.models.ai_session.call_odoo_ai',
            return_value=sentinel,
        ) as mock_iap:
            result = self.session._get_completions(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='sys',
                tools=None,
            )
        mock_iap.assert_called_once()
        self.assertEqual(result, sentinel)

    def test_get_completions_anthropic_skips_iap(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'anthropic',
            'anthropic_enabled': True,
            'anthropic_api_key': 'sk-test',
        })
        fake = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'byo'}],
                'provider_metadata': {},
            }
        }
        with patch(
            'odoo.addons.ai.models.ai_session.call_odoo_ai',
            side_effect=AssertionError('IAP should not be called'),
        ), patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider_name',
            return_value='anthropic',
        ), patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider',
        ) as mock_get:
            provider = MagicMock()
            provider.complete.return_value = fake
            mock_get.return_value = provider
            result = self.session._get_completions(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='sys',
            )
        provider.complete.assert_called_once()
        self.assertEqual(result['result']['content'][0]['text'], 'byo')

    def test_get_completions_openai_skips_iap(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        fake = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'openai'}],
                'provider_metadata': {},
            }
        }
        with patch(
            'odoo.addons.ai.models.ai_session.call_odoo_ai',
            side_effect=AssertionError('IAP should not be called'),
        ), patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider_name',
            return_value='openai',
        ), patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider',
        ) as mock_get:
            provider = MagicMock()
            provider.complete.return_value = fake
            mock_get.return_value = provider
            result = self.session._get_completions(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='sys',
            )
        provider.complete.assert_called_once()
        self.assertEqual(result['result']['content'][0]['text'], 'openai')

    def test_save_and_submit_anthropic_completes_inline(self):
        """Anthropic finishes in-request so the RPC acknowledgement is final."""
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'anthropic',
            'anthropic_enabled': True,
            'anthropic_api_key': 'sk-test',
        })
        fake = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'hello'}],
                'provider_metadata': {},
            }
        }
        callbacks = Callbacks()
        with patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider_name',
            return_value='anthropic',
        ), patch.object(
            self.AiSession, '_publish_response_state',
        ), patch.object(
            self.AiSession, '_ci_ai_complete', return_value=fake,
        ), patch.object(
            self.AiSession, '_continue_agent_loop',
        ) as mock_continue:
            self.session.env.cr.postcommit = callbacks
            self.session._save_and_submit_request(
                {
                    'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                    'instructions': 'sys',
                    'tools': [],
                },
                callback_type='agent_loop',
                request_round=1,
                request_round_limit=30,
                state={},
            )

        self.assertTrue(self.session.request_uuid)
        self.assertFalse(callbacks._funcs)
        mock_continue.assert_called_once()
        self.assertEqual(mock_continue.call_args.args[0]['kind'], 'success')

    def test_save_and_submit_openai_completes_inline(self):
        """OpenAI finishes in-request (same path as Anthropic)."""
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        fake = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'hello'}],
                'provider_metadata': {},
            }
        }
        callbacks = Callbacks()
        with patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider_name',
            return_value='openai',
        ), patch.object(
            self.AiSession, '_publish_response_state',
        ), patch.object(
            self.AiSession, '_ci_ai_complete', return_value=fake,
        ), patch.object(
            self.AiSession, '_continue_agent_loop',
        ) as mock_continue:
            self.session.env.cr.postcommit = callbacks
            self.session._save_and_submit_request(
                {
                    'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                    'instructions': 'sys',
                    'tools': [],
                },
                callback_type='agent_loop',
                request_round=1,
                request_round_limit=30,
                state={},
            )

        self.assertTrue(self.session.request_uuid)
        self.assertFalse(callbacks._funcs)
        mock_continue.assert_called_once()
        self.assertEqual(mock_continue.call_args.args[0]['kind'], 'success')

    def test_save_and_submit_google_completes_inline(self):
        """Google finishes in-request (same path as Anthropic/OpenAI)."""
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
        })
        fake = {
            'result': {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'hello'}],
                'provider_metadata': {},
            }
        }
        callbacks = Callbacks()
        with patch(
            'odoo.addons.ci_ai.models.ai_session.get_chat_provider_name',
            return_value='google',
        ), patch.object(
            self.AiSession, '_publish_response_state',
        ), patch.object(
            self.AiSession, '_ci_ai_complete', return_value=fake,
        ), patch.object(
            self.AiSession, '_continue_agent_loop',
        ) as mock_continue:
            self.session.env.cr.postcommit = callbacks
            self.session._save_and_submit_request(
                {
                    'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                    'instructions': 'sys',
                    'tools': [],
                },
                callback_type='agent_loop',
                request_round=1,
                request_round_limit=30,
                state={},
            )

        self.assertTrue(self.session.request_uuid)
        self.assertFalse(callbacks._funcs)
        mock_continue.assert_called_once()
        self.assertEqual(mock_continue.call_args.args[0]['kind'], 'success')

    def test_chat_byo_does_not_force_embedding_provider(self):
        """Chat BYO leaves embedding_provider unchanged (still iap by default)."""
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'anthropic',
            'anthropic_enabled': True,
            'anthropic_api_key': 'sk-test',
            'embedding_provider': 'iap',
        })
        self.assertEqual(config.embedding_provider, 'iap')

    def test_rescue_posts_error_on_toplevel_chat(self):
        with patch.object(self.AiSession, '_publish_response_state'), patch.object(
            self.AiSession, '_post_ai_response',
        ) as mock_post, patch.object(
            self.AiSession, '_post_turn_notifications',
        ):
            self.session._ci_ai_rescue_session('agent_loop', 'Provider timed out')
        self.assertEqual(self.session.loop_state, 'ready')
        mock_post.assert_called_once()
        self.assertIn('Provider timed out', str(mock_post.call_args.args[0]))
