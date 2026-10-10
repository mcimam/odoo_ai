# Part of ci_ai.

import base64
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.ci_ai.providers.http_security import (
    TRANSCRIPTION_MAX_BYTES,
    decode_transcription_audio,
    is_allowed_google_host,
    is_allowed_openai_host,
    validate_https_base_url,
)
from odoo.addons.ci_ai.tests.ci_ai_common import CiAiTransactionCase


@tagged('post_install', '-at_install')
class TestCiAiHttpSecurity(CiAiTransactionCase):

    @patch('odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips', return_value=True)
    def test_validate_openai_base_url_ok(self, _mock_dns):
        url = validate_https_base_url(
            'https://myresource.openai.azure.com',
            default_url='https://api.openai.com',
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
        )
        self.assertEqual(url, 'https://myresource.openai.azure.com')

    def test_validate_rejects_ip_literal(self):
        with self.assertRaises(ValidationError):
            validate_https_base_url(
                'https://127.0.0.1',
                default_url='https://api.openai.com',
                host_allowed=is_allowed_openai_host,
                field_label='OpenAI Base URL',
            )

    def test_validate_rejects_http_scheme(self):
        with self.assertRaises(ValidationError):
            validate_https_base_url(
                'http://api.openai.com',
                default_url='https://api.openai.com',
                host_allowed=is_allowed_openai_host,
                field_label='OpenAI Base URL',
            )

    @patch('odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips', return_value=False)
    def test_validate_rejects_private_dns(self, _mock_dns):
        with self.assertRaises(ValidationError):
            validate_https_base_url(
                'https://api.openai.com',
                default_url='https://api.openai.com',
                host_allowed=is_allowed_openai_host,
                field_label='OpenAI Base URL',
            )

    def test_decode_transcription_audio_size_limit(self):
        huge = base64.b64encode(b'x' * (TRANSCRIPTION_MAX_BYTES + 1)).decode()
        with self.assertRaises(UserError):
            decode_transcription_audio(huge)

    def test_decode_transcription_audio_ok(self):
        payload = base64.b64encode(b'fake-audio-bytes').decode()
        self.assertEqual(decode_transcription_audio(payload), b'fake-audio-bytes')

    def test_decode_transcription_audio_tolerates_whitespace_and_padding(self):
        payload = base64.b64encode(b'abc').decode().rstrip('=')
        # "abc" encodes to "YWJj" (no pad) — use longer content that needs padding.
        raw = b'abcd'
        payload = base64.b64encode(raw).decode().rstrip('=')
        spaced = payload[:2] + ' \n' + payload[2:]
        self.assertEqual(decode_transcription_audio(spaced), raw)

    def test_config_rejects_bad_openai_base_url(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({
                'openai_gateway': 'custom',
                'openai_base_url': 'https://evil.example.com',
            })

    @patch('odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips', return_value=True)
    def test_validate_google_base_url_ok(self, _mock_dns):
        url = validate_https_base_url(
            'https://generativelanguage.googleapis.com',
            default_url='https://generativelanguage.googleapis.com',
            host_allowed=is_allowed_google_host,
            field_label='Google Base URL',
        )
        self.assertEqual(url, 'https://generativelanguage.googleapis.com')

    def test_config_rejects_bad_google_base_url(self):
        config = self.env['ci.ai.provider.config'].get_solo()
        with self.assertRaises(ValidationError):
            config.write({'google_base_url': 'https://evil.example.com'})

    def test_validate_ollama_rejects_non_default_port(self):
        with self.assertRaises(ValidationError):
            validate_https_base_url(
                'http://127.0.0.1:8080',
                default_url='http://127.0.0.1:11434',
                host_allowed=is_allowed_openai_host,
                field_label='OpenAI Base URL',
                allow_loopback=True,
            )

    def test_validate_ollama_port_11434_ok(self):
        url = validate_https_base_url(
            'http://127.0.0.1:11434',
            default_url='http://127.0.0.1:11434',
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
            allow_loopback=True,
        )
        self.assertEqual(url, 'http://127.0.0.1:11434')
