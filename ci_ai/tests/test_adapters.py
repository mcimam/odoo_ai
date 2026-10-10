# Part of ci_ai.

from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.ci_ai.providers.anthropic_provider import AnthropicChatProvider
from odoo.addons.ci_ai.providers.base import parse_structured_assistant_content
from odoo.addons.ci_ai.providers.google_provider import GoogleChatProvider
from odoo.addons.ci_ai.providers.openai_provider import OpenAIChatProvider
from odoo.addons.ci_ai.providers.router import get_chat_provider, get_chat_provider_name
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiAdapters(CiAiTransactionCase):

    def test_router_iap_returns_none(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({'chat_provider': 'iap'})
        self.assertEqual(get_chat_provider_name(self.env), 'iap')
        self.assertIsNone(get_chat_provider(self.env))

    def test_router_anthropic(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'anthropic',
            'anthropic_enabled': True,
            'anthropic_api_key': 'sk-test',
            'anthropic_model': 'claude-test',
        })
        provider = get_chat_provider(self.env)
        self.assertIsInstance(provider, AnthropicChatProvider)
        self.assertEqual(provider.model, 'claude-test')

    def test_router_openai(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
            'openai_model': 'gpt-test',
        })
        provider = get_chat_provider(self.env)
        self.assertIsInstance(provider, OpenAIChatProvider)
        self.assertEqual(provider.model, 'gpt-test')

    def test_router_google(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        config.write({
            'chat_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
            'google_model': 'gemini-test',
        })
        provider = get_chat_provider(self.env)
        self.assertIsInstance(provider, GoogleChatProvider)
        self.assertEqual(provider.model, 'gemini-test')

    def test_parse_structured_tool_calls(self):
        msg = parse_structured_assistant_content(
            '{"tool_calls":[{"name":"search","call_id":"1","args":{"q":"x"}}]}'
        )
        self.assertEqual(msg['role'], 'assistant')
        self.assertEqual(msg['content'][0]['type'], 'tool_call')
        self.assertEqual(msg['content'][0]['name'], 'search')

    def test_anthropic_complete_maps_tool_use(self):
        provider = AnthropicChatProvider(api_key='sk-test', model='claude-test')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn('/v1/messages', url)
            self.assertEqual(body['model'], 'claude-test')
            self.assertTrue(body['tools'])
            return {
                'content': [
                    {'type': 'text', 'text': 'Calling tool'},
                    {
                        'type': 'tool_use',
                        'id': 'toolu_1',
                        'name': 'ai_tool_web_search',
                        'input': {'search_request': 'odoo'},
                    },
                ]
            }

        with patch(
            'odoo.addons.ci_ai.providers.anthropic_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='Be helpful',
                tools=[{
                    'name': 'ai_tool_web_search',
                    'instructions': 'Search the web',
                    'schema': {'type': 'object', 'properties': {}, 'required': []},
                }],
            )
        content = result['result']['content']
        self.assertEqual(content[0]['type'], 'text')
        self.assertEqual(content[1]['type'], 'tool_call')
        self.assertEqual(content[1]['name'], 'ai_tool_web_search')
        self.assertEqual(content[1]['call_id'], 'toolu_1')

    def test_openai_complete_maps_tool_calls(self):
        provider = OpenAIChatProvider(api_key='sk-test', model='gpt-test')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn('/v1/chat/completions', url)
            self.assertEqual(body['model'], 'gpt-test')
            self.assertEqual(body['messages'][0]['role'], 'system')
            self.assertTrue(body['tools'])
            self.assertEqual(headers['authorization'], 'Bearer sk-test')
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': 'Calling tool',
                        'tool_calls': [{
                            'id': 'call_1',
                            'type': 'function',
                            'function': {
                                'name': 'ai_tool_web_search',
                                'arguments': '{"search_request": "odoo"}',
                            },
                        }],
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='Be helpful',
                tools=[{
                    'name': 'ai_tool_web_search',
                    'instructions': 'Search the web',
                    'schema': {'type': 'object', 'properties': {}, 'required': []},
                }],
            )
        content = result['result']['content']
        self.assertEqual(content[0]['type'], 'text')
        self.assertEqual(content[0]['text'], 'Calling tool')
        self.assertEqual(content[1]['type'], 'tool_call')
        self.assertEqual(content[1]['name'], 'ai_tool_web_search')
        self.assertEqual(content[1]['call_id'], 'call_1')
        self.assertEqual(content[1]['args']['search_request'], 'odoo')

    def test_google_complete_maps_function_calls(self):
        provider = GoogleChatProvider(api_key='AIza-test', model='gemini-test')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn(':generateContent', url)
            self.assertIn('models/gemini-test', url)
            self.assertEqual(headers['x-goog-api-key'], 'AIza-test')
            self.assertTrue(body.get('systemInstruction'))
            self.assertTrue(body.get('tools'))
            self.assertEqual(body['tools'][0]['functionDeclarations'][0]['name'], 'ai_tool_web_search')
            return {
                'candidates': [{
                    'content': {
                        'role': 'model',
                        'parts': [
                            {'text': 'Calling tool'},
                            {
                                'functionCall': {
                                    'name': 'ai_tool_web_search',
                                    'args': {'search_request': 'odoo'},
                                    'id': 'call_g1',
                                },
                            },
                        ],
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}],
                instructions='Be helpful',
                tools=[{
                    'name': 'ai_tool_web_search',
                    'instructions': 'Search the web',
                    'schema': {'type': 'object', 'properties': {}, 'required': []},
                }],
            )
        content = result['result']['content']
        self.assertEqual(content[0]['type'], 'text')
        self.assertEqual(content[0]['text'], 'Calling tool')
        self.assertEqual(content[1]['type'], 'tool_call')
        self.assertEqual(content[1]['name'], 'ai_tool_web_search')
        self.assertEqual(content[1]['call_id'], 'call_g1')
        self.assertEqual(content[1]['args']['search_request'], 'odoo')

    def test_google_complete_maps_function_responses(self):
        provider = GoogleChatProvider(api_key='AIza-test', model='gemini-test')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            roles = [m['role'] for m in body['contents']]
            self.assertIn('model', roles)
            self.assertIn('user', roles)
            user_parts = next(m['parts'] for m in body['contents'] if m['role'] == 'user')
            self.assertTrue(any('functionResponse' in p for p in user_parts))
            return {
                'candidates': [{
                    'content': {
                        'role': 'model',
                        'parts': [{'text': 'Done'}],
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[
                    {
                        'role': 'assistant',
                        'content': [{
                            'type': 'tool_call',
                            'name': 'ai_tool_web_search',
                            'call_id': 'call_g1',
                            'args': {'q': 'x'},
                        }],
                    },
                    {
                        'role': 'user',
                        'content': [{
                            'type': 'tool_result',
                            'tool_call_id': 'call_g1',
                            'tool_name': 'ai_tool_web_search',
                            'success': True,
                            'result': {'text': 'found'},
                        }],
                    },
                ],
                instructions='sys',
            )
        self.assertEqual(result['result']['content'][0]['text'], 'Done')

    def test_openai_complete_maps_tool_results(self):
        provider = OpenAIChatProvider(api_key='sk-test', model='gpt-test')

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            roles = [m['role'] for m in body['messages']]
            self.assertIn('tool', roles)
            tool_msg = next(m for m in body['messages'] if m['role'] == 'tool')
            self.assertEqual(tool_msg['tool_call_id'], 'call_1')
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': 'Done',
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[
                    {
                        'role': 'assistant',
                        'content': [{
                            'type': 'tool_call',
                            'name': 'ai_tool_web_search',
                            'call_id': 'call_1',
                            'args': {'q': 'x'},
                        }],
                    },
                    {
                        'role': 'user',
                        'content': [{
                            'type': 'tool_result',
                            'tool_call_id': 'call_1',
                            'tool_name': 'ai_tool_web_search',
                            'success': True,
                            'result': [{'type': 'text', 'text': 'found'}],
                        }],
                    },
                ],
                instructions='sys',
            )
        self.assertEqual(result['result']['content'][0]['text'], 'Done')

    def test_openai_complete_passes_response_schema(self):
        provider = OpenAIChatProvider(api_key='sk-test', model='gpt-test')
        review_schema = {
            'type': 'object',
            'properties': {
                'safe': {'type': 'boolean'},
                'reason': {'type': 'string'},
            },
            'required': ['safe', 'reason'],
            'additionalProperties': False,
        }

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertEqual(body['response_format']['type'], 'json_schema')
            sent = body['response_format']['json_schema']['schema']
            self.assertEqual(sent['additionalProperties'], False)
            self.assertEqual(set(sent['required']), {'safe', 'reason'})
            self.assertTrue(body['response_format']['json_schema']['strict'])
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': '```json\n{"safe": true, "reason": ""}\n```',
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'review'}]}],
                instructions='Reviewer',
                schema=review_schema,
            )
        self.assertEqual(result['result']['content'][0]['text'], '{"safe": true, "reason": ""}')

    def test_openai_normalizes_odoo_schemas_for_strict_mode(self):
        provider = OpenAIChatProvider(api_key='sk-test', model='gpt-test')
        # Mirrors ai_website shapes schema: missing additionalProperties + optional fields.
        shapes_schema = {
            'type': 'object',
            'properties': {
                'placements': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'section_index': {'type': 'integer'},
                            'shape': {'type': 'string'},
                            'edge': {'type': 'string', 'enum': ['top', 'bottom']},
                            'reason': {'type': 'string'},
                        },
                        'required': ['section_index', 'shape', 'reason'],
                    },
                },
            },
            'required': ['placements'],
        }

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            sent = body['response_format']['json_schema']['schema']
            self.assertFalse(sent['additionalProperties'])
            items = sent['properties']['placements']['items']
            self.assertFalse(items['additionalProperties'])
            self.assertEqual(
                set(items['required']),
                {'section_index', 'shape', 'edge', 'reason'},
            )
            self.assertEqual(items['properties']['edge']['type'], ['string', 'null'])
            self.assertIn(None, items['properties']['edge']['enum'])
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': '{"placements":[]}',
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'shapes'}]}],
                instructions='Shapes',
                schema=shapes_schema,
            )
        self.assertEqual(result['result']['content'][0]['text'], '{"placements":[]}')

    def test_anthropic_complete_passes_output_schema(self):
        provider = AnthropicChatProvider(api_key='sk-test', model='claude-test')
        review_schema = {
            'type': 'object',
            'properties': {
                'safe': {'type': 'boolean'},
                'reason': {'type': 'string'},
            },
            'required': ['safe', 'reason'],
            'additionalProperties': False,
        }

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertEqual(body['output_config']['format']['type'], 'json_schema')
            self.assertEqual(body['output_config']['format']['schema'], review_schema)
            return {'content': [{'type': 'text', 'text': '{"safe": false, "reason": "xss"}'}]}

        with patch(
            'odoo.addons.ci_ai.providers.anthropic_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.complete(
                messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'review'}]}],
                instructions='Reviewer',
                schema=review_schema,
            )
        self.assertEqual(
            result['result']['content'][0]['text'],
            '{"safe": false, "reason": "xss"}',
        )
