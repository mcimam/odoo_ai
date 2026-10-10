# Part of ci_ai.

import base64
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.ci_ai.providers.google_provider import (
    GoogleImageProvider,
    GoogleTranscriptionProvider,
)
from odoo.addons.ci_ai.providers.openai_provider import (
    OpenAIImageProvider,
    OpenAITranscriptionProvider,
)
from odoo.addons.ci_ai.providers.router import (
    get_image_provider,
    get_image_provider_name,
    get_stt_provider,
    get_stt_provider_name,
)
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiSttAndImage(CiAiTransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ci.ai.provider.config'].get_solo().write({
            'chat_provider': 'iap',
            'embedding_provider': 'iap',
            'stt_provider': 'iap',
            'image_provider': 'iap',
            'openai_enabled': False,
            'openai_api_key': False,
            'openai_stt_model': 'whisper-1',
            'openai_realtime_stt_model': 'gpt-live-transcribe',
            'openai_image_model': 'dall-e-3',
            'google_enabled': False,
            'google_api_key': False,
            'google_stt_model': 'gemini-2.5-flash',
            'google_image_model': 'gemini-2.5-flash-image',
        })

    def test_router_stt_openai(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'stt_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        self.assertEqual(get_stt_provider_name(self.env), 'openai')
        provider = get_stt_provider(self.env)
        self.assertIsInstance(provider, OpenAITranscriptionProvider)
        self.assertEqual(provider.realtime_model, 'gpt-live-transcribe')

    def test_router_image_openai(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'image_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        self.assertEqual(get_image_provider_name(self.env), 'openai')
        self.assertIsInstance(get_image_provider(self.env), OpenAIImageProvider)

    def test_stt_requires_openai_credentials(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'stt_provider': 'openai',
                'openai_enabled': False,
                'openai_api_key': 'sk-test',
            })

    def test_image_requires_openai_credentials(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'image_provider': 'openai',
                'openai_enabled': True,
                'openai_api_key': '',
            })

    def test_openai_transcribe_text(self):
        provider = OpenAITranscriptionProvider(api_key='sk-test', model='whisper-1')
        audio_b64 = base64.b64encode(b'fake-audio').decode()

        def fake_multipart(provider_label, url, headers, fields, files, *, boundary, timeout=180):
            self.assertIn('/v1/audio/transcriptions', url)
            self.assertEqual(fields['model'], 'whisper-1')
            self.assertEqual(fields['response_format'], 'text')
            self.assertEqual(files[0][0], 'file')
            return b'hello world'

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_multipart_post',
            side_effect=fake_multipart,
        ):
            result = provider.transcribe(audio_b64, response_format='text')
        self.assertEqual(result['text'], 'hello world')

    def test_openai_transcribe_vtt(self):
        provider = OpenAITranscriptionProvider(api_key='sk-test')
        audio_b64 = base64.b64encode(b'fake-audio').decode()

        def fake_multipart(provider_label, url, headers, fields, files, *, boundary, timeout=180):
            self.assertEqual(fields['response_format'], 'vtt')
            return b'WEBVTT\n\n00:00.000 --> 00:01.000\nHi'

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_multipart_post',
            side_effect=fake_multipart,
        ):
            result = provider.transcribe(audio_b64, response_format='vtt')
        self.assertIn('WEBVTT', result['text'])

    def test_openai_create_realtime_session(self):
        provider = OpenAITranscriptionProvider(
            api_key='sk-test',
            realtime_model='gpt-live-transcribe',
        )

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertEqual(method, 'POST')
            self.assertIn('/v1/realtime/client_secrets', url)
            self.assertEqual(body['session']['type'], 'transcription')
            transcription = body['session']['audio']['input']['transcription']
            self.assertEqual(transcription['model'], 'gpt-live-transcribe')
            self.assertEqual(transcription['languages'], ['en'])
            self.assertEqual(transcription['prompt'], 'meeting notes')
            self.assertIsNone(body['session']['audio']['input']['turn_detection'])
            return {
                'value': 'ek_test_token',
                'expires_at': 1700000000,
                'session': {'type': 'transcription'},
            }

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.create_realtime_session(
                language='en',
                prompt='meeting notes',
            )
        self.assertEqual(result['session_token'], 'ek_test_token')
        self.assertEqual(result['expires_at'], 1700000000)
        self.assertEqual(result['model'], 'gpt-live-transcribe')

    def test_get_session_token_openai(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'stt_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
            'openai_realtime_stt_model': 'gpt-live-transcribe',
        })
        from odoo.addons.ci_ai.controllers.ai import AIController

        controller = AIController()
        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            return_value={'value': 'ek_live', 'expires_at': 1},
        ), patch('odoo.addons.ci_ai.controllers.ai.request') as mock_request:
            mock_request.env = self.env
            result = controller.get_session_token('en', 'prompt')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['session_token'], 'ek_live')
        self.assertTrue(result['ci_ai_realtime'])
        self.assertFalse(result['iap_transaction_token'])

    def test_get_session_token_google_blocked(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'stt_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
        })
        from odoo.addons.ci_ai.controllers.ai import AIController

        controller = AIController()
        with patch('odoo.addons.ci_ai.controllers.ai.request') as mock_request:
            mock_request.env = self.env
            result = controller.get_session_token('en', 'prompt')
        self.assertEqual(result['status'], 'error')
        self.assertIn('batch transcription only', result['message'])

    def test_openai_image_generate(self):
        provider = OpenAIImageProvider(api_key='sk-test', model='dall-e-3')
        png_b64 = base64.b64encode(b'fakepng').decode()

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn('/v1/images/generations', url)
            self.assertEqual(body['model'], 'dall-e-3')
            self.assertEqual(body['response_format'], 'b64_json')
            self.assertEqual(body['size'], '1024x1024')
            return {'data': [{'b64_json': png_b64}]}

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            side_effect=fake_http,
        ):
            parts = provider.generate('a cat', aspect_ratio='1:1')
        self.assertEqual(parts[0]['type'], 'inline_data')
        self.assertEqual(parts[0]['data'], png_b64)
        self.assertEqual(parts[0]['mimetype'], 'image/png')

    def test_generate_image_attachments_openai_skips_iap_path(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'image_provider': 'openai',
            'openai_enabled': True,
            'openai_api_key': 'sk-test',
        })
        png_b64 = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 32).decode()

        with patch(
            'odoo.addons.ci_ai.providers.openai_provider.http_json',
            return_value={'data': [{'b64_json': png_b64}]},
        ), patch.object(
            type(self.env['ai.session']),
            '_get_direct_response',
            side_effect=AssertionError('IAP image path should not be called'),
        ):
            result, attachments = self.env['ai.tool']._generate_image_attachments(
                prompt='logo',
                images_paths=None,
                image_title='Logo',
                aspect_ratio='1:1',
            )
        self.assertTrue(result)
        self.assertEqual(result[0]['type'], 'inline_data')
        self.assertTrue(attachments)
        self.assertIn('attachment_id', result[0].get('metadata') or {})

    def test_settings_stt_image_openai(self):
        settings = self.env['res.config.settings'].create({
            'ci_ai_openai_enabled': True,
            'ci_ai_openai_api_key': 'sk-openai',
            'ci_ai_openai_stt_model': 'whisper-1',
            'ci_ai_openai_realtime_stt_model': 'gpt-live-transcribe',
            'ci_ai_openai_image_model': 'dall-e-3',
            'ci_ai_stt_provider': 'openai',
            'ci_ai_image_provider': 'openai',
        })
        settings.execute()
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertEqual(config.stt_provider, 'openai')
        self.assertEqual(config.image_provider, 'openai')
        self.assertEqual(config.openai_stt_model, 'whisper-1')
        self.assertEqual(config.openai_realtime_stt_model, 'gpt-live-transcribe')
        self.assertEqual(config.openai_image_model, 'dall-e-3')

    def test_router_stt_google(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'stt_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
        })
        self.assertEqual(get_stt_provider_name(self.env), 'google')
        provider = get_stt_provider(self.env)
        self.assertIsInstance(provider, GoogleTranscriptionProvider)
        self.assertEqual(provider.model, 'gemini-2.5-flash')

    def test_router_image_google(self):
        self.env['ci.ai.provider.config'].get_solo().write({
            'image_provider': 'google',
            'google_enabled': True,
            'google_api_key': 'AIza-test',
        })
        self.assertEqual(get_image_provider_name(self.env), 'google')
        self.assertIsInstance(get_image_provider(self.env), GoogleImageProvider)

    def test_stt_requires_google_credentials(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'stt_provider': 'google',
                'google_enabled': False,
                'google_api_key': 'AIza-test',
            })

    def test_image_requires_google_credentials(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'image_provider': 'google',
                'google_enabled': True,
                'google_api_key': '',
            })

    def test_google_transcribe_text(self):
        provider = GoogleTranscriptionProvider(api_key='AIza-test', model='gemini-2.5-flash')
        audio_b64 = base64.b64encode(b'fake-audio').decode()

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn(':generateContent', url)
            self.assertEqual(headers['x-goog-api-key'], 'AIza-test')
            parts = body['contents'][0]['parts']
            self.assertEqual(parts[0]['inlineData']['data'], audio_b64)
            self.assertEqual(parts[0]['inlineData']['mimeType'], 'audio/mp3')
            return {
                'candidates': [{
                    'content': {'parts': [{'text': 'hello world'}]},
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            side_effect=fake_http,
        ):
            result = provider.transcribe(audio_b64, mimetype='audio/mp3', language='en')
        self.assertEqual(result['text'], 'hello world')

    def test_google_image_generate(self):
        provider = GoogleImageProvider(api_key='AIza-test', model='gemini-2.5-flash-image')
        png_b64 = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 8).decode()

        def fake_http(provider_label, method, url, headers, body=None, timeout=120):
            self.assertIn(':generateContent', url)
            self.assertIn('IMAGE', body['generationConfig']['responseModalities'])
            self.assertEqual(body['generationConfig']['imageConfig']['aspectRatio'], '1:1')
            return {
                'candidates': [{
                    'content': {
                        'parts': [{
                            'inlineData': {
                                'mimeType': 'image/png',
                                'data': png_b64,
                            },
                        }],
                    },
                }],
            }

        with patch(
            'odoo.addons.ci_ai.providers.google_provider.http_json',
            side_effect=fake_http,
        ):
            parts = provider.generate('a logo', aspect_ratio='1:1')
        self.assertEqual(parts[0]['type'], 'inline_data')
        self.assertEqual(parts[0]['data'], png_b64)
        self.assertEqual(parts[0]['mimetype'], 'image/png')

    def test_settings_stt_image_google(self):
        settings = self.env['res.config.settings'].create({
            'ci_ai_google_enabled': True,
            'ci_ai_google_api_key': 'AIza-google',
            'ci_ai_google_stt_model': 'gemini-2.5-flash',
            'ci_ai_google_image_model': 'gemini-2.5-flash-image',
            'ci_ai_stt_provider': 'google',
            'ci_ai_image_provider': 'google',
        })
        settings.execute()
        config = self.env['ci.ai.provider.config'].get_solo()
        self.assertEqual(config.stt_provider, 'google')
        self.assertEqual(config.image_provider, 'google')
        self.assertEqual(config.google_stt_model, 'gemini-2.5-flash')
        self.assertEqual(config.google_image_model, 'gemini-2.5-flash-image')
