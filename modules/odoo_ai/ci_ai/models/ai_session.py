# Part of ci_ai.

"""Override ai.session transport to route chat through CI providers."""

from __future__ import annotations

import copy
import logging
import uuid

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.ci_ai.providers.router import get_chat_provider, get_chat_provider_name

_logger = logging.getLogger(__name__)


class AiSession(models.Model):
    _inherit = 'ai.session'

    def _ci_ai_complete(self, messages, instructions, tools=None, **options):
        provider_name = get_chat_provider_name(self.env)
        provider = get_chat_provider(self.env)
        if provider is None:
            raise UserError(self.env._('Chat provider is set to Odoo IAP; use the stock path.'))
        _logger.debug(
            'CI AI chat call provider=%s model=%s messages=%s tools=%s session=%s',
            provider_name,
            getattr(provider, 'model', None),
            len(messages or []),
            len(tools or []),
            self.id,
        )
        return provider.complete(
            messages=messages,
            instructions=instructions,
            tools=tools,
            **options,
        )

    def _get_completions(self, messages, instructions, tools=None, **options):
        provider_name = get_chat_provider_name(self.env)
        if provider_name == 'iap':
            _logger.debug(
                'CI AI chat call provider=iap messages=%s tools=%s session=%s',
                len(messages or []),
                len(tools or []),
                self.id,
            )
            return super()._get_completions(messages, instructions, tools=tools, **options)
        return self._ci_ai_complete(messages, instructions, tools=tools, **options)

    def _ci_ai_apply_completion(self, callback_type, completion_payload):
        """Run provider completion and continue the matching session callback."""
        self.ensure_one()
        response = self._ci_ai_complete(
            messages=completion_payload.get('messages') or [],
            instructions=completion_payload.get('instructions') or '',
            tools=completion_payload.get('tools'),
            **{
                k: v for k, v in completion_payload.items()
                if k not in ('messages', 'instructions', 'tools')
            },
        )
        completion_result = {
            'kind': 'success',
            'message': response['result'],
        }
        env = self.env(context={
            **self.env.context,
            'discuss_channel': self.channel_id,
        })
        session = self.with_env(env).sudo()
        match callback_type:
            case 'agent_loop':
                session._continue_agent_loop(completion_result)
            case 'channel_name':
                session._continue_channel_name(completion_result)
            case _:
                session._continue_agent_loop(completion_result)

    def _ci_ai_rescue_session(self, callback_type, error_msg):
        self.ensure_one()
        if callback_type == 'channel_name':
            self.unlink()
            return
        # Always post the error on top-level chats. Stock IAP often uses
        # content=None here (credit notifs elsewhere); silent fail leaves
        # users with "Thinking" ending and no reply.
        self._finish_exchange('failed', content=error_msg or self.env._(
            'Custom AI provider failed. Please try again later.'
        ))

    def _save_and_submit_request(
        self, payload, *, callback_type,
        request_round, request_round_limit,
        state,
    ) -> None:
        if get_chat_provider_name(self.env) == 'iap':
            return super()._save_and_submit_request(
                payload,
                callback_type=callback_type,
                request_round=request_round,
                request_round_limit=request_round_limit,
                state=state,
            )

        self.ensure_one()
        guest = self.env.context.get('guest')
        vals = {
            'loop_state': 'waiting_model',
            'request_uuid': str(uuid.uuid4()),
            'request_webhook_secret': uuid.uuid4().hex,
            'request_round': request_round,
            'request_round_limit': request_round_limit,
            'request_payload': payload,
            'request_user_id': self.env.uid,
            'request_guest_id': guest.id if guest else False,
            'request_context': self._get_request_context_snapshot(),
            'resume_token': False,
            'pending_tool_call': False,
        }
        state = dict(state or {})
        state['callback_type'] = callback_type
        vals['state'] = state
        self.write(vals)
        self._publish_response_state()

        completion_payload = copy.deepcopy(payload)
        # BYO providers must complete in-request so /ai/start_session_advance
        # returns the final loop_state. Otherwise the client applies
        # acknowledgement waiting_model after bus already delivered ready and
        # the UI stays stuck on "Thinking".
        try:
            self._ci_ai_apply_completion(callback_type, completion_payload)
        except UserError as err:
            _logger.warning('CI AI provider user error for %s: %s', vals['request_uuid'], err)
            self._ci_ai_rescue_session(callback_type, str(err) or self.env._(
                'Custom AI provider failed. Please try again later.'
            ))
        except Exception:  # noqa: BLE001
            _logger.exception('CI AI provider failed for request %s', vals['request_uuid'])
            self._ci_ai_rescue_session(
                callback_type,
                'Custom AI provider is currently unreachable. Please try again later.',
            )
