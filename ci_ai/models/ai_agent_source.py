# Part of ci_ai.

"""Ensure knowledge sources index with a real embedding model."""

from __future__ import annotations

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AiAgentSource(models.Model):
    _inherit = 'ai.agent.source'

    def _trigger_embedding_generation(self):
        """Fall back to the provider default when the agent has no embedding model.

        Stock creates ``ai.embedding`` rows with ``embedding_model=NULL`` when the
        agent field is empty. The generate-embeddings cron then skips those rows
        (``embedding_model != False``), so the source stays forever on Processing.
        """
        for source in self:
            agent = source.agent_id
            if agent and not agent.embedding_model:
                agent._ci_ai_ensure_embedding_model()
        # Repair orphan chunk rows that stock created with NULL embedding_model.
        self._ci_ai_repair_null_embedding_models()
        return super()._trigger_embedding_generation()

    def _ci_ai_repair_null_embedding_models(self):
        """Fix chunk rows created with a NULL embedding model and re-trigger generation."""
        Embedding = self.env['ai.embedding']
        default = Embedding._get_default_embedding_model()
        if not default:
            return Embedding.browse()

        broken = Embedding.search([
            ('embedding_model', '=', False),
            ('embedding_vector', '=', False),
        ])
        if not broken:
            return broken

        # Ensure owning agents also get a model when we can resolve them.
        attachment_ids = broken.filtered(lambda e: e.res_model == 'ir.attachment').mapped('res_id')
        if attachment_ids:
            sources = self.search([('attachment_id', 'in', attachment_ids)])
            sources.mapped('agent_id')._ci_ai_ensure_embedding_model()

        _logger.info(
            'CI AI: repairing %s embedding rows with NULL model -> %s',
            len(broken), default,
        )
        broken.write({
            'embedding_model': default,
            'has_embedding_generation_failed': False,
            'embedding_error': False,
        })
        self.env.ref('ai.ir_cron_generate_embedding')._trigger()
        return broken
