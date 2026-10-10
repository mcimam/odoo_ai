# Part of ci_ai.

"""Override ai.embedding transport to route embeddings through CI providers."""

from __future__ import annotations

import logging

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.ci_ai.providers.google_provider import (
    DEFAULT_EMBEDDING_MODEL as GOOGLE_DEFAULT_EMBEDDING_MODEL,
)
from odoo.addons.ci_ai.providers.openai_provider import DEFAULT_EMBEDDING_MODEL
from odoo.addons.ci_ai.providers.router import (
    get_embedding_provider,
    get_embedding_provider_name,
)

_logger = logging.getLogger(__name__)


class AiEmbedding(models.Model):
    _inherit = 'ai.embedding'

    @api.model
    def _get_embeddings(self, input, model, mode):
        provider_name = get_embedding_provider_name(self.env)
        if provider_name == 'iap':
            _logger.debug(
                'CI AI embedding call provider=iap model=%s mode=%s inputs=%s',
                model, mode, len(input or []),
            )
            return super()._get_embeddings(input, model, mode)
        provider = get_embedding_provider(self.env)
        if provider is None:
            raise UserError(self.env._(
                'Embedding provider is set to Odoo IAP; use the stock path.'
            ))
        _logger.debug(
            'CI AI embedding call provider=%s model=%s mode=%s inputs=%s',
            provider_name,
            model or getattr(provider, 'model', None),
            mode,
            len(input or []),
        )
        return provider.embed(inputs=input, model=model, mode=mode)

    @api.model
    def _get_default_embedding_model(self):
        # No ormcache here: selection depends on live provider config.
        # BYO paths never hit IAP, so return the configured model even in tests.
        provider_name = get_embedding_provider_name(self.env)
        config = self.env['ci.ai.provider.config'].get_solo()
        if provider_name == 'openai':
            return (config.openai_embedding_model or DEFAULT_EMBEDDING_MODEL).strip()
        if provider_name == 'google':
            return (config.google_embedding_model or GOOGLE_DEFAULT_EMBEDDING_MODEL).strip()
        return super()._get_default_embedding_model()

    @api.model
    def _get_supported_embedding_models(self):
        provider_name = get_embedding_provider_name(self.env)
        config = self.env['ci.ai.provider.config'].get_solo()
        if provider_name == 'openai':
            model = (config.openai_embedding_model or DEFAULT_EMBEDDING_MODEL).strip()
            # Keep a small allow-list so switching models does not mass-invalidate
            # existing vectors unexpectedly; both 3-* variants use dimensions=1536.
            supported = {
                model,
                DEFAULT_EMBEDDING_MODEL,
                'text-embedding-3-large',
                'text-embedding-ada-002',
            }
            return sorted(supported)
        if provider_name == 'google':
            model = (config.google_embedding_model or GOOGLE_DEFAULT_EMBEDDING_MODEL).strip()
            supported = {
                model,
                GOOGLE_DEFAULT_EMBEDDING_MODEL,
            }
            return sorted(supported)
        return super()._get_supported_embedding_models()
