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


def odoo_tools_to_prompt_block(tools: list[dict] | None) -> str:
    if not tools:
        return ''
    lines = [
        'You may call tools by replying with ONLY a JSON object of the form:',
        '{"tool_calls":[{"name":"<tool>","call_id":"<id>","args":{...}}]}',
        'or a normal text answer (no JSON wrapper) when no tool is needed.',
        'Available tools:',
    ]
    for tool in tools:
        lines.append(f"- {tool.get('name')}: {tool.get('instructions') or ''}")
        if tool.get('schema'):
            lines.append(f"  schema: {json.dumps(tool['schema'])}")
    return '\n'.join(lines)


def pack_messages_for_prompt(messages: list[dict], instructions: str, tools: list[dict] | None) -> str:
    chunks = [instructions or '', odoo_tools_to_prompt_block(tools)]
    for msg in messages or []:
        role = msg.get('role', 'user')
        chunks.append(f'[{role}]\n{parts_to_text(msg.get("content"))}')
    return '\n\n'.join(c for c in chunks if c)


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


def schema_instruction(schema: dict | None) -> str:
    """Prompt appendix for providers that cannot enforce JSON schema natively."""
    if not schema:
        return ''
    return (
        'Respond with ONLY a single JSON object that validates against this JSON Schema. '
        'Do not wrap it in markdown fences or add commentary.\n'
        f'{json.dumps(schema)}'
    )


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
