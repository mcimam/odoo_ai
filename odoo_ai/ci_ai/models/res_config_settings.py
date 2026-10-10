# Part of ci_ai.

from odoo import api, fields, models

from odoo.addons.ci_ai.providers.openai_gateways import (
    OPENAI_GATEWAY_SELECTION,
    get_gateway_preset,
)

from .ci_ai_provider_config import CAPABILITY_PROVIDERS, CHAT_PROVIDERS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Stored on the transient settings record (not related) so Save writes the
    # singleton in one shot. Related inverses write field-by-field and trip
    # multi-field constraints (e.g. enable + API key) mid-save.

    ci_ai_chat_provider = fields.Selection(
        selection=CHAT_PROVIDERS,
        string='Chat',
        required=True,
        default='iap',
        groups='base.group_system',
    )
    ci_ai_embedding_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Embeddings / RAG',
        required=True,
        default='iap',
        groups='base.group_system',
    )
    ci_ai_stt_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Speech-to-text',
        required=True,
        default='iap',
        groups='base.group_system',
    )
    ci_ai_image_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Image generation',
        required=True,
        default='iap',
        groups='base.group_system',
    )

    ci_ai_anthropic_enabled = fields.Boolean(
        string='Anthropic',
        groups='base.group_system',
    )
    ci_ai_anthropic_api_key = fields.Char(
        string='API Key',
        groups='base.group_system',
    )
    ci_ai_anthropic_model = fields.Char(
        string='Model',
        groups='base.group_system',
    )
    ci_ai_anthropic_base_url = fields.Char(
        string='Base URL',
        groups='base.group_system',
    )

    ci_ai_openai_enabled = fields.Boolean(
        string='OpenAI',
        groups='base.group_system',
    )
    ci_ai_openai_gateway = fields.Selection(
        selection=OPENAI_GATEWAY_SELECTION,
        string='Gateway',
        default='openai',
        groups='base.group_system',
    )
    ci_ai_openai_api_key = fields.Char(
        string='API Key',
        groups='base.group_system',
    )
    ci_ai_openai_model = fields.Char(
        string='Chat Model',
        groups='base.group_system',
    )
    ci_ai_openai_embedding_model = fields.Char(
        string='Embedding Model',
        groups='base.group_system',
    )
    ci_ai_openai_stt_model = fields.Char(
        string='Speech-to-text Model',
        groups='base.group_system',
    )
    ci_ai_openai_realtime_stt_model = fields.Char(
        string='Realtime STT Model',
        groups='base.group_system',
    )
    ci_ai_openai_image_model = fields.Char(
        string='Image Model',
        groups='base.group_system',
    )
    ci_ai_openai_base_url = fields.Char(
        string='Base URL',
        groups='base.group_system',
    )

    ci_ai_google_enabled = fields.Boolean(
        string='Google',
        groups='base.group_system',
    )
    ci_ai_google_api_key = fields.Char(
        string='API Key',
        groups='base.group_system',
    )
    ci_ai_google_model = fields.Char(
        string='Chat Model',
        groups='base.group_system',
    )
    ci_ai_google_embedding_model = fields.Char(
        string='Embedding Model',
        groups='base.group_system',
    )
    ci_ai_google_stt_model = fields.Char(
        string='Speech-to-text Model',
        groups='base.group_system',
    )
    ci_ai_google_image_model = fields.Char(
        string='Image Model',
        groups='base.group_system',
    )
    ci_ai_google_base_url = fields.Char(
        string='Base URL',
        groups='base.group_system',
    )

    @api.onchange('ci_ai_openai_gateway')
    def _onchange_ci_ai_openai_gateway(self):
        for rec in self:
            preset = get_gateway_preset(rec.ci_ai_openai_gateway)
            if preset.get('base_url'):
                rec.ci_ai_openai_base_url = preset['base_url']
            if preset.get('default_chat_model'):
                rec.ci_ai_openai_model = preset['default_chat_model']

    @api.model
    def get_values(self):
        res = super().get_values()
        config = self.env['ci.ai.provider.config'].get_solo()
        res.update({
            'ci_ai_chat_provider': config.chat_provider,
            'ci_ai_embedding_provider': config.embedding_provider,
            'ci_ai_stt_provider': config.stt_provider,
            'ci_ai_image_provider': config.image_provider,
            'ci_ai_anthropic_enabled': config.anthropic_enabled,
            'ci_ai_anthropic_api_key': config.anthropic_api_key,
            'ci_ai_anthropic_model': config.anthropic_model,
            'ci_ai_anthropic_base_url': config.anthropic_base_url,
            'ci_ai_openai_enabled': config.openai_enabled,
            'ci_ai_openai_gateway': config.openai_gateway,
            'ci_ai_openai_api_key': config.openai_api_key,
            'ci_ai_openai_model': config.openai_model,
            'ci_ai_openai_embedding_model': config.openai_embedding_model,
            'ci_ai_openai_stt_model': config.openai_stt_model,
            'ci_ai_openai_realtime_stt_model': config.openai_realtime_stt_model,
            'ci_ai_openai_image_model': config.openai_image_model,
            'ci_ai_openai_base_url': config.openai_base_url,
            'ci_ai_google_enabled': config.google_enabled,
            'ci_ai_google_api_key': config.google_api_key,
            'ci_ai_google_model': config.google_model,
            'ci_ai_google_embedding_model': config.google_embedding_model,
            'ci_ai_google_stt_model': config.google_stt_model,
            'ci_ai_google_image_model': config.google_image_model,
            'ci_ai_google_base_url': config.google_base_url,
        })
        return res

    def set_values(self):
        super().set_values()
        self.env['ci.ai.provider.config'].get_solo().write({
            'chat_provider': self.ci_ai_chat_provider,
            'embedding_provider': self.ci_ai_embedding_provider,
            'stt_provider': self.ci_ai_stt_provider,
            'image_provider': self.ci_ai_image_provider,
            'anthropic_enabled': self.ci_ai_anthropic_enabled,
            'anthropic_api_key': self.ci_ai_anthropic_api_key,
            'anthropic_model': self.ci_ai_anthropic_model,
            'anthropic_base_url': self.ci_ai_anthropic_base_url,
            'openai_enabled': self.ci_ai_openai_enabled,
            'openai_gateway': self.ci_ai_openai_gateway or 'openai',
            'openai_api_key': self.ci_ai_openai_api_key,
            'openai_model': self.ci_ai_openai_model,
            'openai_embedding_model': self.ci_ai_openai_embedding_model,
            'openai_stt_model': self.ci_ai_openai_stt_model,
            'openai_realtime_stt_model': self.ci_ai_openai_realtime_stt_model,
            'openai_image_model': self.ci_ai_openai_image_model,
            'openai_base_url': self.ci_ai_openai_base_url,
            'google_enabled': self.ci_ai_google_enabled,
            'google_api_key': self.ci_ai_google_api_key,
            'google_model': self.ci_ai_google_model,
            'google_embedding_model': self.ci_ai_google_embedding_model,
            'google_stt_model': self.ci_ai_google_stt_model,
            'google_image_model': self.ci_ai_google_image_model,
            'google_base_url': self.ci_ai_google_base_url,
        })
