# Part of ci_ai.

"""Anthropic Messages API chat adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

from odoo.exceptions import UserError, ValidationError

from .base import coerce_schema_text_parts, completion_response, parts_to_text
from .http_security import (
    build_api_url,
    http_json,
    is_allowed_anthropic_host,
    validate_https_base_url,
)

_logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = '2023-06-01'
DEFAULT_ANTHROPIC_BASE_URL = 'https://api.anthropic.com'


def _normalize_anthropic_base_url(base_url: str) -> str:
    try:
        return validate_https_base_url(
            base_url,
            default_url=DEFAULT_ANTHROPIC_BASE_URL,
            host_allowed=is_allowed_anthropic_host,
            field_label='Anthropic Base URL',
        )
    except ValidationError as err:
        raise UserError(str(err)) from err


def _odoo_tools_to_anthropic(tools: list[dict] | None) -> list[dict]:
    result = []
    for tool in tools or []:
        schema = tool.get('schema') or {'type': 'object', 'properties': {}, 'required': []}
        result.append({
            'name': tool['name'],
            'description': tool.get('instructions') or tool['name'],
            'input_schema': schema,
        })
    return result


def _odoo_messages_to_anthropic(messages: list[dict]) -> list[dict]:
    out = []
    for msg in messages or []:
        role = msg.get('role')
        if role == 'assistant':
            content: list[Any] = []
            for part in msg.get('content') or []:
                if part.get('type') == 'text':
                    content.append({'type': 'text', 'text': part.get('text') or ''})
                elif part.get('type') == 'tool_call':
                    content.append({
                        'type': 'tool_use',
                        'id': str(part.get('call_id') or part.get('name')),
                        'name': part.get('name'),
                        'input': part.get('args') or {},
                    })
            if content:
                out.append({'role': 'assistant', 'content': content})
        elif role == 'user':
            content = []
            for part in msg.get('content') or []:
                if part.get('type') == 'text':
                    content.append({'type': 'text', 'text': part.get('text') or ''})
                elif part.get('type') == 'tool_result':
                    content.append({
                        'type': 'tool_result',
                        'tool_use_id': str(part.get('tool_call_id') or ''),
                        'content': parts_to_text(part.get('result')) or json.dumps(part.get('result'), default=str),
                        'is_error': not part.get('success', True),
                    })
                elif part.get('type') == 'inline_data':
                    content.append({'type': 'text', 'text': '[inline attachment omitted]'})
            if content:
                out.append({'role': 'user', 'content': content})
    return out


def _anthropic_content_to_odoo(content: list[dict]) -> dict:
    parts: list[dict] = []
    for block in content or []:
        btype = block.get('type')
        if btype == 'text':
            parts.append({'type': 'text', 'text': block.get('text') or ''})
        elif btype == 'tool_use':
            parts.append({
                'type': 'tool_call',
                'name': block.get('name'),
                'args': block.get('input') or {},
                'call_id': block.get('id'),
            })
    if not parts:
        parts = [{'type': 'text', 'text': ''}]
    return {'role': 'assistant', 'content': parts, 'provider_metadata': {}}


class AnthropicChatProvider:
    """Chat completions via Anthropic Messages API."""

    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_ANTHROPIC_BASE_URL):
        self.api_key = (api_key or '').strip()
        self.model = model or 'claude-sonnet-4-6'
        self.base_url = _normalize_anthropic_base_url(base_url or DEFAULT_ANTHROPIC_BASE_URL)

    def complete(self, messages, instructions, tools=None, **options):
        if not self.api_key:
            raise UserError('Anthropic API key is not configured.')

        schema = options.get('schema')
        _logger.debug(
            'Anthropic chat complete model=%s base_url=%s messages=%s tools=%s schema=%s',
            self.model, self.base_url, len(messages or []), len(tools or []), bool(schema),
        )
        body: dict[str, Any] = {
            'model': self.model,
            'max_tokens': int(options.get('max_tokens') or 4096),
            'system': instructions or '',
            'messages': _odoo_messages_to_anthropic(messages),
        }
        anthropic_tools = _odoo_tools_to_anthropic(tools)
        if anthropic_tools:
            body['tools'] = anthropic_tools

        if schema:
            body['output_config'] = {
                'format': {
                    'type': 'json_schema',
                    'schema': schema,
                },
            }

        headers = {
            'content-type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': ANTHROPIC_VERSION,
        }
        url = build_api_url(self.base_url, '/v1/messages')
        response = http_json('Anthropic', 'POST', url, headers, body)
        assistant = _anthropic_content_to_odoo(response.get('content') or [])
        if schema:
            assistant = coerce_schema_text_parts(assistant)
        return completion_response(assistant)
