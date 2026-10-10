# Part of ci_ai.

"""Route generate_image through OpenAI Images API when configured."""

from __future__ import annotations

import base64
import logging

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.ai.utils.ai_image_tools import closest_aspect_ratio, field_to_image_path
from odoo.addons.ci_ai.providers.router import get_image_provider, get_image_provider_name

_logger = logging.getLogger(__name__)


class AiTool(models.AbstractModel):
    _inherit = 'ai.tool'

    @api.model
    def _generate_image_attachments(self, prompt, images_paths, image_title, aspect_ratio='1:1'):
        provider_name = get_image_provider_name(self.env)
        if provider_name == 'iap':
            _logger.debug(
                'CI AI image call provider=iap title=%s aspect_ratio=%s refs=%s',
                image_title, aspect_ratio, len(images_paths or []),
            )
            return super()._generate_image_attachments(
                prompt, images_paths, image_title, aspect_ratio,
            )

        provider = get_image_provider(self.env)
        if provider is None:
            raise UserError(self.env._(
                'Image provider is set to Odoo IAP; use the stock path.'
            ))

        if images_paths:
            _logger.info(
                'CI AI image generation (%s) ignores %s reference image path(s); '
                'prompt-only generation is used.',
                provider_name,
                len(images_paths),
            )

        ratio = closest_aspect_ratio(aspect_ratio=aspect_ratio)
        _logger.debug(
            'CI AI image call provider=%s model=%s title=%s aspect_ratio=%s prompt_len=%s',
            provider_name,
            getattr(provider, 'model', None),
            image_title,
            ratio,
            len(prompt or ''),
        )
        inline_data_parts = provider.generate(prompt, aspect_ratio=ratio)

        attachment_vals = [{
            'raw': part['data'],
            'mimetype': part['mimetype'],
            'name': f'AI Generated {image_title}',
            'description': f'AI Generated {image_title}',
        } for part in inline_data_parts]
        parts_by_checksum = {
            self.env['ir.attachment']._compute_checksum(base64.b64decode(part['data'])): part
            for part in inline_data_parts
        }
        attachments = self.env['ai.attachment.vacuum']._create_attachments_and_mark_unused(
            attachment_vals,
        )
        for attachment in attachments:
            part = parts_by_checksum[attachment.checksum]
            part['metadata'] = {
                'image_path': field_to_image_path(attachment, 'raw'),
                'attachment_id': attachment.id,
            }
        return inline_data_parts, attachments
