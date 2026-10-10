# Part of ci_ai.

"""Override AI transcription routes for OpenAI batch + realtime STT."""

from __future__ import annotations

import logging

from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ai.controllers import ai as ai_controller
from odoo.addons.iap import InsufficientCreditError
from odoo.addons.ci_ai.providers.http_security import decode_transcription_audio
from odoo.addons.ci_ai.providers.router import get_stt_provider, get_stt_provider_name

_logger = logging.getLogger(__name__)


class AIController(ai_controller.AIController):
    @http.route()
    def transcribe(self, audio_base64, language=None):
        provider_name = get_stt_provider_name(request.env)
        if provider_name == 'iap':
            _logger.debug('CI AI STT HTTP call provider=iap language=%s', language)
            return super().transcribe(audio_base64, language=language)

        if not audio_base64:
            raise BadRequest('No audio data provided')

        try:
            decode_transcription_audio(audio_base64)
        except UserError as err:
            raise BadRequest(str(err)) from err

        provider = get_stt_provider(request.env)
        _logger.debug(
            'CI AI STT HTTP call provider=%s model=%s language=%s payload_chars=%s',
            provider_name,
            getattr(provider, 'model', None),
            language,
            len(audio_base64 or ''),
        )
        try:
            response = provider.transcribe(
                audio_base64,
                mimetype='audio/mp3',
                language=language,
                response_format='text',
            )
            return {
                'status': 'success',
                'text': response.get('text') or '',
            }
        except InsufficientCreditError:
            return {'status': 'insufficient_credit'}
        except UserError as err:
            raise BadRequest(str(err)) from err

    @http.route()
    def get_session_token(self, language: str, prompt: str):
        provider_name = get_stt_provider_name(request.env)
        if provider_name == 'google':
            _logger.debug('CI AI realtime STT blocked provider=google language=%s', language)
            return {
                'status': 'error',
                'message': (
                    'Google speech-to-text supports batch transcription only. '
                    'Use OpenAI or Odoo AI (IAP) for live browser STT.'
                ),
            }
        if provider_name != 'openai':
            _logger.debug('CI AI realtime STT call provider=iap language=%s', language)
            return super().get_session_token(language, prompt)

        provider = get_stt_provider(request.env)
        _logger.debug(
            'CI AI realtime STT call provider=openai model=%s language=%s',
            getattr(provider, 'realtime_model', None),
            language,
        )
        try:
            session = provider.create_realtime_session(
                language=language,
                prompt=prompt,
            )
            return {
                'status': 'success',
                'session_token': session['session_token'],
                # Stock UI still stores/reports this; OpenAI has no IAP billing handle.
                'iap_transaction_token': False,
                'ci_ai_realtime': True,
                'ci_ai_realtime_model': session.get('model'),
            }
        except UserError as err:
            _logger.warning('OpenAI realtime STT session failed: %s', err)
            return {
                'status': 'error',
                'message': str(err),
            }

    @http.route()
    def report_usage(self, iap_transaction_token, usage):
        if get_stt_provider_name(request.env) in ('openai', 'google'):
            _logger.debug(
                'CI AI realtime STT usage ignored provider=%s token=%s',
                get_stt_provider_name(request.env),
                bool(iap_transaction_token),
            )
            return False
        if not iap_transaction_token:
            return False
        return super().report_usage(iap_transaction_token, usage)
