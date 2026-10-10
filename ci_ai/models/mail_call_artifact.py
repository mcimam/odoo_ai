# Part of ci_ai.

"""Route call-recording STT through CI providers when configured."""

from __future__ import annotations

import base64
import logging

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.ci_ai.providers.router import get_stt_provider, get_stt_provider_name
from odoo.addons.iap import InsufficientCreditError

_logger = logging.getLogger(__name__)


class MailCallArtifact(models.Model):
    _inherit = 'mail.call.artifact'

    def _transcribe_claimed_record(self, lease_until):
        provider_name = get_stt_provider_name(self.env)
        if provider_name == 'iap':
            _logger.debug('CI AI STT call provider=iap artifact=%s', self.id)
            return super()._transcribe_claimed_record(lease_until)

        self.ensure_one()
        if not self._is_lease_valid(lease_until):
            return {'status': 'skip'}

        # Keep the same size guard as stock (OpenAI Whisper 25MB limit).
        max_size = 25 * 1024 * 1024
        if self.media_id.file_size > max_size:
            return {'status': 'file_too_large'}

        data = self.media_id.raw
        if not data:
            return {'status': 'no_media'}

        provider = get_stt_provider(self.env)
        if provider is None:
            raise UserError(self.env._(
                'Speech-to-text provider is set to Odoo IAP; use the stock path.'
            ))
        _logger.debug(
            'CI AI STT call provider=%s model=%s artifact=%s bytes=%s mimetype=%s',
            provider_name,
            getattr(provider, 'model', None),
            self.id,
            len(data),
            self.media_id.mimetype or 'audio/mp3',
        )
        try:
            response = provider.transcribe(
                base64.b64encode(data).decode('utf-8'),
                mimetype=self.media_id.mimetype or 'audio/mp3',
                response_format='vtt',
            )
            text_vtt = response.get('text')
            if text_vtt is None:
                return {'status': 'err'}
            return {'status': 'ok', 'transcript': text_vtt}
        except (InsufficientCreditError, UserError):
            _logger.error(
                'CI AI transcription failed provider=%s for call.artifact %s',
                provider_name, self.id,
            )
            return {'status': 'err'}
