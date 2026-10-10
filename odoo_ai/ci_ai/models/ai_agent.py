# Part of ci_ai.

"""Ensure agents always have a usable embedding model for RAG indexing."""

from __future__ import annotations

import logging

from odoo import api, models

from odoo.addons.ci_ai.providers.router import get_embedding_provider_name

_logger = logging.getLogger(__name__)


class AiAgent(models.Model):
    _inherit = 'ai.agent'

    @api.model_create_multi
    def create(self, vals_list):
        agents = super().create(vals_list)
        # Stock create can leave embedding_model empty (install_mode, failed IAP
        # default, or pre-OpenAI agents). Fill from the active provider default.
        agents._ci_ai_ensure_embedding_model()
        return agents

    def _ci_ai_ensure_embedding_model(self):
        """Set a default embedding model when missing so RAG indexing can proceed."""
        missing = self.filtered(lambda a: not a.embedding_model)
        if not missing:
            return
        default = self.env['ai.embedding']._get_default_embedding_model()
        if not default:
            _logger.warning(
                'CI AI: cannot set embedding_model on agents %s; no default model',
                missing.ids,
            )
            return
        _logger.info(
            'CI AI: setting embedding_model=%s on agents %s (provider=%s)',
            default, missing.ids, get_embedding_provider_name(self.env),
        )
        missing.write({'embedding_model': default})
