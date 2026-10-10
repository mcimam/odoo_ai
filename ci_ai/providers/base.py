# Part of ci_ai.

"""Shared helpers to map Odoo AI message TypedDicts to provider APIs."""

from __future__ import annotations

import json
from typing import Any


def parts_to_text(parts: list[dict] | None) -> str:
    if not parts:
        return ''
    texts = []
    for part in parts:
        if part.get('type') == 'text' and part.get('text'):
            texts.append(part['text'])
        elif part.get('type') == 'tool_result':
            texts.append(json.dumps({
                'tool_result': {
                    'tool_name': part.get('tool_name'),
                    'tool_call_id': part.get('tool_call_id'),
                    'success': part.get('success'),
                    'result': part.get('result'),
                }
            }, default=str))
    return '\n'.join(texts)


def format_embedding_input(item: Any) -> str:
    """Normalize RAG / embedding inputs (str or ``{title, content}``) to text."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item or '')
    title = (item.get('title') or '').strip()
    content = (item.get('content') or '').strip()
    if title and content:
        return f'{title}\n\n{content}'
    return content or title


def parse_structured_assistant_content(text: str) -> dict:
    """Parse structured JSON tool-call text into an Odoo AssistantMessage."""
    content: list[dict[str, Any]] = []
    stripped = (text or '').strip()
    if not stripped:
        return {'role': 'assistant', 'content': [{'type': 'text', 'text': ''}], 'provider_metadata': {}}

    candidate = stripped
    if candidate.startswith('```'):
        candidate = candidate.strip('`')
        if candidate.startswith('json'):
            candidate = candidate[4:].strip()

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict) and data.get('tool_calls'):
        for call in data['tool_calls']:
            content.append({
                'type': 'tool_call',
                'name': call.get('name'),
                'args': call.get('args') or {},
                'call_id': call.get('call_id') or call.get('id') or call.get('name'),
            })
        if data.get('text'):
            content.insert(0, {'type': 'text', 'text': data['text']})
        return {'role': 'assistant', 'content': content, 'provider_metadata': {}}

    return {
        'role': 'assistant',
        'content': [{'type': 'text', 'text': stripped}],
        'provider_metadata': {},
    }


def completion_response(assistant_message: dict) -> dict:
    return {'result': assistant_message}


def strip_json_fences(text: str) -> str:
    """Remove optional markdown code fences around a JSON payload."""
    stripped = (text or '').strip()
    if not stripped.startswith('```'):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def coerce_schema_text_parts(assistant_message: dict) -> dict:
    """Normalize assistant text when a completion schema was requested."""
    content = assistant_message.get('content') or []
    changed = False
    new_content = []
    for part in content:
        if part.get('type') == 'text' and isinstance(part.get('text'), str):
            cleaned = strip_json_fences(part['text'])
            if cleaned != part['text']:
                changed = True
                new_content.append({**part, 'text': cleaned})
            else:
                new_content.append(part)
        else:
            new_content.append(part)
    if not changed:
        return assistant_message
    return {**assistant_message, 'content': new_content}
