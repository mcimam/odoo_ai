# Part of ci_ai.

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.ci_ai.providers.http_security import (
    is_allowed_anthropic_host,
    is_allowed_google_host,
    is_allowed_openai_host,
    validate_https_base_url,
)
from odoo.addons.ci_ai.providers.openai_gateways import (
    OPENAI_GATEWAY_SELECTION,
    gateway_supports,
    get_gateway_preset,
    resolve_gateway_base_url,
)


CHAT_PROVIDERS = [
    ('iap', 'Odoo AI (IAP)'),
    ('anthropic', 'Anthropic'),
    ('openai', 'OpenAI / Compatible'),
    ('google', 'Google (Gemini)'),
]

CAPABILITY_PROVIDERS = [
    ('iap', 'Odoo AI (IAP)'),
    ('openai', 'OpenAI / Compatible'),
    ('google', 'Google (Gemini)'),
]

class CiAiProviderConfig(models.Model):
    _name = 'ci.ai.provider.config'
    _description = 'CI AI Provider Configuration'
    _rec_name = 'name'

    name = fields.Char(default='AI Providers', required=True, translate=True)

    anthropic_enabled = fields.Boolean(
        string='Enable Anthropic',
        default=False,
        groups='base.group_system',
    )
    openai_enabled = fields.Boolean(
        string='Enable OpenAI',
        default=False,
        groups='base.group_system',
    )
    google_enabled = fields.Boolean(
        string='Enable Google',
        default=False,
        groups='base.group_system',
    )

    anthropic_api_key = fields.Char(string='Anthropic API Key', groups='base.group_system')
    openai_api_key = fields.Char(string='OpenAI API Key', groups='base.group_system')
    google_api_key = fields.Char(string='Google API Key', groups='base.group_system')
    openai_gateway = fields.Selection(
        selection=OPENAI_GATEWAY_SELECTION,
        string='OpenAI Gateway',
        default='openai',
        required=True,
        groups='base.group_system',
        help='OpenAI-compatible endpoint. Named presets fix the host; Azure / Custom / '
             'Ollama use Base URL. Chat works on all presets; embeddings / batch STT / '
             'image require OpenAI, Azure, or OpenRouter (Ollama: chat + embeddings). '
             'OpenRouter has no realtime browser STT.',
    )
    anthropic_base_url = fields.Char(
        string='Anthropic Base URL',
        default='https://api.anthropic.com',
        groups='base.group_system',
        help='HTTPS only. Allowed host: api.anthropic.com (validated on save).',
    )
    openai_base_url = fields.Char(
        string='OpenAI Base URL',
        default='https://api.openai.com',
        groups='base.group_system',
        help='Used for Azure, Custom, and Ollama. Named SaaS presets ignore this field '
             'and use their built-in host. HTTPS only (HTTP allowed for Ollama localhost).',
    )
    google_base_url = fields.Char(
        string='Google Base URL',
        default='https://generativelanguage.googleapis.com',
        groups='base.group_system',
        help='HTTPS only. Allowed: generativelanguage.googleapis.com and '
             'aiplatform.googleapis.com (validated on save). AI Studio key first; '
             'Vertex later.',
    )
    anthropic_model = fields.Char(
        string='Anthropic Model',
        default='claude-sonnet-4-6',
        groups='base.group_system',
        help='API model id, e.g. claude-sonnet-4-6 or claude-sonnet-5. '
             'claude-sonnet-4-20250514 was retired June 2026.',
    )
    openai_model = fields.Char(
        string='OpenAI Model',
        default='gpt-4o',
        groups='base.group_system',
        help='Chat Completions model id, e.g. gpt-4o or gpt-4.1.',
    )
    openai_embedding_model = fields.Char(
        string='OpenAI Embedding Model',
        default='text-embedding-3-small',
        groups='base.group_system',
        help='Embeddings model id. Must produce 1536-dim vectors (use dimensions=1536 '
             'for text-embedding-3-*). Default: text-embedding-3-small.',
    )
    openai_stt_model = fields.Char(
        string='OpenAI Speech-to-text Model',
        default='whisper-1',
        groups='base.group_system',
        help='Batch audio transcriptions model id (Whisper). Default: whisper-1.',
    )
    openai_realtime_stt_model = fields.Char(
        string='OpenAI Realtime Speech-to-text Model',
        default='gpt-live-transcribe',
        groups='base.group_system',
        help='Realtime browser STT model id. Default: gpt-live-transcribe.',
    )
    openai_image_model = fields.Char(
        string='OpenAI Image Model',
        default='dall-e-3',
        groups='base.group_system',
        help='Images API model id, e.g. dall-e-3 or gpt-image-1.',
    )
    google_model = fields.Char(
        string='Google Chat Model',
        default='gemini-2.5-flash',
        groups='base.group_system',
        help='Gemini chat model id, e.g. gemini-2.5-flash or gemini-2.5-pro.',
    )
    google_embedding_model = fields.Char(
        string='Google Embedding Model',
        default='gemini-embedding-001',
        groups='base.group_system',
        help='Gemini embedding model. Uses outputDimensionality=1536 for Odoo Vector size.',
    )
    google_stt_model = fields.Char(
        string='Google Speech-to-text Model',
        default='gemini-2.5-flash',
        groups='base.group_system',
        help='Gemini multimodal model used for batch audio transcription. '
             'Realtime browser STT is not supported yet for Google.',
    )
    google_image_model = fields.Char(
        string='Google Image Model',
        default='gemini-2.5-flash-image',
        groups='base.group_system',
        help='Gemini image model id, e.g. gemini-2.5-flash-image.',
    )

    chat_provider = fields.Selection(
        selection=CHAT_PROVIDERS,
        string='Chat',
        default='iap',
        required=True,
        groups='base.group_system',
    )
    embedding_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Embeddings / RAG',
        default='iap',
        required=True,
        groups='base.group_system',
        help='OpenAI / Google use 1536-dimensional vectors (Odoo Vector size). '
             'Switching providers may require re-embedding agent sources.',
    )
    stt_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Speech-to-text',
        default='iap',
        required=True,
        groups='base.group_system',
        help='OpenAI/Azure: Whisper batch + gpt-live-transcribe realtime. '
             'OpenRouter: batch Whisper only (no realtime). '
             'Google: Gemini multimodal batch STT (no realtime yet).',
    )
    image_provider = fields.Selection(
        selection=CAPABILITY_PROVIDERS,
        string='Image generation',
        default='iap',
        required=True,
        groups='base.group_system',
        help='OpenAI Images API or Gemini image models for the generate_image tool.',
    )

    @api.onchange('openai_gateway')
    def _onchange_openai_gateway(self):
        for rec in self:
            preset = get_gateway_preset(rec.openai_gateway)
            if preset.get('base_url'):
                rec.openai_base_url = preset['base_url']
            if preset.get('default_chat_model'):
                rec.openai_model = preset['default_chat_model']

    @api.constrains('openai_base_url', 'openai_gateway')
    def _check_openai_base_url(self):
        for rec in self:
            preset = get_gateway_preset(rec.openai_gateway)
            effective = resolve_gateway_base_url(rec.openai_gateway, rec.openai_base_url)
            if rec.openai_gateway in ('azure', 'custom') and not (rec.openai_base_url or '').strip():
                raise ValidationError(self.env._(
                    'OpenAI Base URL is required for Azure OpenAI and Custom gateways.'
                ))
            validate_https_base_url(
                effective,
                default_url=preset.get('base_url') or 'https://api.openai.com',
                host_allowed=is_allowed_openai_host,
                field_label='OpenAI Base URL',
                allow_path=bool(preset.get('allow_path')),
                allow_loopback=bool(preset.get('allow_loopback')),
            )

    @api.constrains('anthropic_base_url')
    def _check_anthropic_base_url(self):
        for rec in self:
            validate_https_base_url(
                rec.anthropic_base_url or 'https://api.anthropic.com',
                default_url='https://api.anthropic.com',
                host_allowed=is_allowed_anthropic_host,
                field_label='Anthropic Base URL',
            )

    @api.constrains('google_base_url')
    def _check_google_base_url(self):
        for rec in self:
            validate_https_base_url(
                rec.google_base_url or 'https://generativelanguage.googleapis.com',
                default_url='https://generativelanguage.googleapis.com',
                host_allowed=is_allowed_google_host,
                field_label='Google Base URL',
            )

    @api.constrains(
        'chat_provider',
        'embedding_provider',
        'stt_provider',
        'image_provider',
        'anthropic_enabled',
        'openai_enabled',
        'google_enabled',
        'anthropic_api_key',
        'openai_api_key',
        'google_api_key',
        'openai_gateway',
    )
    def _check_provider_credentials(self):
        for rec in self:
            if rec.chat_provider == 'anthropic':
                if not rec.anthropic_enabled:
                    raise ValidationError(self.env._(
                        'Enable Anthropic before selecting it as the Chat provider.'
                    ))
                if not (rec.anthropic_api_key or '').strip():
                    raise ValidationError(self.env._(
                        'Anthropic API key is required when Chat provider is Anthropic.'
                    ))
            if rec.chat_provider == 'openai':
                rec._ci_ai_require_openai_capability('chat', self.env._('Chat'))
            if rec.chat_provider == 'google':
                rec._ci_ai_require_google(self.env._('Chat'))
            if rec.embedding_provider == 'openai':
                rec._ci_ai_require_openai_capability(
                    'embedding', self.env._('Embeddings / RAG'),
                )
            if rec.embedding_provider == 'google':
                rec._ci_ai_require_google(self.env._('Embeddings / RAG'))
            if rec.stt_provider == 'openai':
                rec._ci_ai_require_openai_capability(
                    'stt', self.env._('Speech-to-text'),
                )
            if rec.stt_provider == 'google':
                rec._ci_ai_require_google(self.env._('Speech-to-text'))
            if rec.image_provider == 'openai':
                rec._ci_ai_require_openai_capability(
                    'image', self.env._('Image generation'),
                )
            if rec.image_provider == 'google':
                rec._ci_ai_require_google(self.env._('Image generation'))
            if rec.anthropic_enabled and not (rec.anthropic_api_key or '').strip():
                raise ValidationError(self.env._(
                    'Anthropic API key is required when Anthropic is enabled.'
                ))
            if rec.openai_enabled and not (rec.openai_api_key or '').strip():
                raise ValidationError(self.env._(
                    'OpenAI API key is required when OpenAI is enabled.'
                ))
            if rec.google_enabled and not (rec.google_api_key or '').strip():
                raise ValidationError(self.env._(
                    'Google API key is required when Google is enabled.'
                ))

    @api.model
    def get_solo(self):
        """Return the singleton config row (create if missing)."""
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({'name': 'AI Providers'})
        elif not config.name:
            config.name = 'AI Providers'
        return config

    def _ci_ai_require_openai(self, capability_label):
        self.ensure_one()
        if not self.openai_enabled:
            raise ValidationError(self.env._(
                'Enable OpenAI before selecting it as the %s provider.',
                capability_label,
            ))
        if not (self.openai_api_key or '').strip():
            raise ValidationError(self.env._(
                'OpenAI API key is required when %s provider is OpenAI.',
                capability_label,
            ))

    def _ci_ai_require_google(self, capability_label):
        self.ensure_one()
        if not self.google_enabled:
            raise ValidationError(self.env._(
                'Enable Google before selecting it as the %s provider.',
                capability_label,
            ))
        if not (self.google_api_key or '').strip():
            raise ValidationError(self.env._(
                'Google API key is required when %s provider is Google.',
                capability_label,
            ))

    def _ci_ai_require_openai_capability(self, capability_key, capability_label):
        self.ensure_one()
        self._ci_ai_require_openai(capability_label)
        if not gateway_supports(self.openai_gateway, capability_key):
            raise ValidationError(self.env._(
                'Gateway "%(gateway)s" does not support %(capability)s. '
                'Use OpenAI, Azure, or OpenRouter for full batch capabilities, '
                'Ollama for chat + embeddings, or route %(capability)s to '
                'Odoo AI (IAP) / Google.',
                gateway=dict(OPENAI_GATEWAY_SELECTION).get(
                    self.openai_gateway, self.openai_gateway,
                ),
                capability=capability_label,
            ))
