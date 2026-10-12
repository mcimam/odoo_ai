# Part of ci_ai.

"""OpenAI Chat Completions, Embeddings, STT, and Images adapters."""

from __future__ import annotations

import base64
import copy
import json
import logging
import mimetypes
import uuid
from typing import Any

from odoo.exceptions import UserError, ValidationError

from .base import (
    coerce_schema_text_parts,
    completion_response,
    format_embedding_input,
    parts_to_text,
)
from .http_security import (
    build_api_url,
    decode_transcription_audio,
    http_json,
    http_multipart_post,
    is_allowed_openai_host,
    sanitize_mimetype,
    validate_https_base_url,
)
from .openai_gateways import (
    gateway_supports,
    get_gateway_preset,
    resolve_gateway_base_url,
)

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://api.openai.com'
DEFAULT_MODEL = 'gpt-4o'
DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small'
DEFAULT_STT_MODEL = 'whisper-1'
DEFAULT_REALTIME_STT_MODEL = 'gpt-live-transcribe'
DEFAULT_IMAGE_MODEL = 'dall-e-3'
EMBEDDING_DIMENSIONS = 1536

# Models that take ``languages`` (list) instead of singular ``language``.
_REALTIME_LANGUAGES_MODELS = frozenset({
    'gpt-live-transcribe',
    'gpt-transcribe',
})

_LANDSCAPE_RATIOS = frozenset({'21:9', '16:9', '5:4', '4:3', '3:2', '5:3'})
_PORTRAIT_RATIOS = frozenset({'9:16', '4:5', '3:4', '2:3'})


def _make_nullable(prop: dict) -> None:
    """Mark a JSON-schema property as optional under OpenAI strict mode."""
    if not isinstance(prop, dict):
        return
    if 'anyOf' in prop or 'oneOf' in prop:
        return
    prop_type = prop.get('type')
    if prop_type is None:
        return
    if isinstance(prop_type, list):
        if 'null' not in prop_type:
            prop['type'] = [*prop_type, 'null']
    else:
        prop['type'] = [prop_type, 'null']
    if 'enum' in prop and isinstance(prop['enum'], list) and None not in prop['enum']:
        prop['enum'] = [*prop['enum'], None]


def normalize_openai_strict_schema(schema: dict) -> dict:
    """Adapt Odoo completion schemas to OpenAI Structured Outputs (strict).

    OpenAI requires every object to set ``additionalProperties: false`` and list
    every property in ``required``. Optional fields become nullable types.
    """
    if not isinstance(schema, dict):
        raise UserError('OpenAI response schema must be an object.')

    node = copy.deepcopy(schema)

    def walk(current: Any) -> None:
        if isinstance(current, list):
            for item in current:
                walk(item)
            return
        if not isinstance(current, dict):
            return

        for key in ('items', 'contains', 'not'):
            if key in current:
                walk(current[key])
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            if isinstance(current.get(key), list):
                walk(current[key])
        for key in ('$defs', 'definitions', 'patternProperties', 'properties'):
            value = current.get(key)
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)

        is_object = current.get('type') == 'object' or 'properties' in current
        if not is_object:
            return

        current['type'] = 'object'
        current['additionalProperties'] = False
        properties = current.get('properties')
        if not isinstance(properties, dict):
            current.setdefault('properties', {})
            current.setdefault('required', [])
            return

        original_required = set(current.get('required') or [])
        for name, prop in properties.items():
            if name not in original_required:
                _make_nullable(prop)
        current['required'] = list(properties.keys())

    walk(node)
    return node


def _normalize_openai_base_url(base_url: str, gateway: str | None = 'openai') -> str:
    preset = get_gateway_preset(gateway)
    effective = resolve_gateway_base_url(gateway, base_url)
    fallback = preset.get('base_url') or DEFAULT_BASE_URL
    try:
        return validate_https_base_url(
            effective,
            default_url=fallback,
            host_allowed=is_allowed_openai_host,
            field_label='OpenAI Base URL',
            allow_path=bool(preset.get('allow_path')),
            allow_loopback=bool(preset.get('allow_loopback')),
        )
    except ValidationError as err:
        raise UserError(str(err)) from err


def _require_gateway_capability(gateway: str | None, capability: str, label: str) -> None:
    if gateway_supports(gateway, capability):
        return
    raise UserError(
        'The selected OpenAI-compatible gateway does not support %s. '
        'Route %s to Odoo AI (IAP), Google, or OpenAI / Azure / OpenRouter, '
        'or switch the OpenAI gateway preset.'
        % (label, label)
    )


def _is_openrouter(gateway: str | None) -> bool:
    return (gateway or '') == 'openrouter'


def _openrouter_model(model: str | None) -> str:
    """Prefix bare OpenAI model ids with ``openai/`` for OpenRouter slugs."""
    api_model = (model or '').strip()
    if not api_model or '/' in api_model:
        return api_model
    return f'openai/{api_model}'


def _embedding_model_supports_dimensions(model: str | None) -> bool:
    """True for text-embedding-3-* (bare or ``openai/``-prefixed)."""
    bare = (model or '').strip().rsplit('/', 1)[-1]
    return bare.startswith('text-embedding-3')


def _openai_auth_headers(api_key: str, base_url: str) -> dict[str, str]:
    headers = {
        'content-type': 'application/json',
        'authorization': f'Bearer {api_key}',
    }
    # OpenRouter asks for these attribution headers on chat requests.
    host = (base_url or '').lower()
    if 'openrouter.ai' in host:
        headers.setdefault('HTTP-Referer', 'https://www.odoo.com')
        headers.setdefault('X-Title', 'Odoo CI AI')
    return headers


def _format_seconds_as_vtt(seconds: float | int | None) -> str:
    """Format a timestamp as ``HH:MM:SS.mmm`` for WebVTT cues."""
    total_ms = max(0, int(round(float(seconds or 0) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}'


def _verbose_json_to_webvtt(payload: dict[str, Any]) -> str:
    """Build a minimal WebVTT document from OpenRouter verbose_json STT."""
    segments = payload.get('segments') or []
    lines = ['WEBVTT', '']
    if segments:
        for index, segment in enumerate(segments, start=1):
            start = _format_seconds_as_vtt(segment.get('start'))
            end = _format_seconds_as_vtt(segment.get('end'))
            text = (segment.get('text') or '').strip()
            if not text:
                continue
            lines.append(str(index))
            lines.append(f'{start} --> {end}')
            lines.append(text)
            lines.append('')
        return '\n'.join(lines).rstrip() + '\n'
    text = (payload.get('text') or '').strip()
    if not text:
        return 'WEBVTT\n'
    lines.extend(['1', '00:00:00.000 --> 00:00:01.000', text, ''])
    return '\n'.join(lines)


def _mimetype_to_extension(mimetype: str | None) -> str:
    mime = sanitize_mimetype(mimetype)
    if mime == 'application/octet-stream':
        mime = 'audio/mpeg'
    ext = mimetypes.guess_extension(mime) or ''
    if ext:
        return ext.lstrip('.')
    aliases = {
        'audio/mp3': 'mp3',
        'audio/mpeg': 'mp3',
        'audio/mp4': 'mp4',
        'audio/webm': 'webm',
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
        'audio/ogg': 'ogg',
        'video/webm': 'webm',
    }
    return aliases.get(mime, 'mp3')


def _aspect_ratio_to_size(aspect_ratio: str | None, model: str) -> str:
    ratio = (aspect_ratio or '1:1').strip()
    if model.startswith('dall-e-3'):
        if ratio in _LANDSCAPE_RATIOS:
            return '1792x1024'
        if ratio in _PORTRAIT_RATIOS:
            return '1024x1792'
        return '1024x1024'
    # gpt-image-1 and compatible
    if ratio in _LANDSCAPE_RATIOS:
        return '1536x1024'
    if ratio in _PORTRAIT_RATIOS:
        return '1024x1536'
    return '1024x1024'


def _odoo_tools_to_openai(tools: list[dict] | None) -> list[dict]:
    result = []
    for tool in tools or []:
        schema = tool.get('schema') or {'type': 'object', 'properties': {}, 'required': []}
        result.append({
            'type': 'function',
            'function': {
                'name': tool['name'],
                'description': tool.get('instructions') or tool['name'],
                'parameters': schema,
            },
        })
    return result


def _odoo_messages_to_openai(messages: list[dict], instructions: str) -> list[dict]:
    out: list[dict] = []
    if instructions:
        out.append({'role': 'system', 'content': instructions})

    for msg in messages or []:
        role = msg.get('role')
        if role == 'assistant':
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            for part in msg.get('content') or []:
                if part.get('type') == 'text':
                    text_parts.append(part.get('text') or '')
                elif part.get('type') == 'tool_call':
                    tool_calls.append({
                        'id': str(part.get('call_id') or part.get('name')),
                        'type': 'function',
                        'function': {
                            'name': part.get('name'),
                            'arguments': json.dumps(part.get('args') or {}),
                        },
                    })
            assistant_msg: dict[str, Any] = {'role': 'assistant'}
            content = '\n'.join(t for t in text_parts if t)
            if content or not tool_calls:
                assistant_msg['content'] = content
            else:
                assistant_msg['content'] = None
            if tool_calls:
                assistant_msg['tool_calls'] = tool_calls
            out.append(assistant_msg)
        elif role == 'user':
            text_chunks: list[str] = []
            tool_results: list[dict] = []
            for part in msg.get('content') or []:
                if part.get('type') == 'text':
                    text_chunks.append(part.get('text') or '')
                elif part.get('type') == 'tool_result':
                    tool_results.append({
                        'role': 'tool',
                        'tool_call_id': str(part.get('tool_call_id') or ''),
                        'content': parts_to_text(part.get('result')) or json.dumps(
                            part.get('result'), default=str,
                        ),
                    })
                elif part.get('type') == 'inline_data':
                    text_chunks.append('[inline attachment omitted]')
            if text_chunks:
                out.append({'role': 'user', 'content': '\n'.join(text_chunks)})
            out.extend(tool_results)
    return out


def _openai_message_to_odoo(message: dict) -> dict:
    parts: list[dict] = []
    content = message.get('content')
    if isinstance(content, str) and content:
        parts.append({'type': 'text', 'text': content})
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                parts.append({'type': 'text', 'text': block.get('text') or ''})
            elif isinstance(block, str) and block:
                parts.append({'type': 'text', 'text': block})

    for call in message.get('tool_calls') or []:
        function = call.get('function') or {}
        raw_args = function.get('arguments') or '{}'
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError:
            args = {'_raw': raw_args}
        if not isinstance(args, dict):
            args = {'_value': args}
        parts.append({
            'type': 'tool_call',
            'name': function.get('name'),
            'args': args,
            'call_id': call.get('id') or function.get('name'),
        })

    if not parts:
        parts = [{'type': 'text', 'text': ''}]
    return {'role': 'assistant', 'content': parts, 'provider_metadata': {}}


class OpenAIChatProvider:
    """Chat completions via OpenAI Chat Completions API (or compatible gateway)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        gateway: str = 'openai',
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_MODEL
        self.gateway = gateway or 'openai'
        self.base_url = _normalize_openai_base_url(
            base_url or DEFAULT_BASE_URL, gateway=self.gateway,
        )

    def complete(self, messages, instructions, tools=None, **options):
        if not self.api_key:
            raise UserError('OpenAI API key is not configured.')
        _require_gateway_capability(self.gateway, 'chat', 'Chat')

        schema = options.get('schema')
        _logger.debug(
            'OpenAI chat complete gateway=%s model=%s base_url=%s messages=%s tools=%s schema=%s',
            self.gateway, self.model, self.base_url,
            len(messages or []), len(tools or []), bool(schema),
        )
        body: dict[str, Any] = {
            'model': self.model,
            'messages': _odoo_messages_to_openai(messages, instructions or ''),
        }
        openai_tools = _odoo_tools_to_openai(tools)
        if openai_tools:
            body['tools'] = openai_tools

        max_tokens = options.get('max_tokens')
        if max_tokens:
            body['max_tokens'] = int(max_tokens)

        # Odoo passes CompletionOptions.schema for structured replies (e.g. website
        # safety reviewer). Without response_format the model returns prose and
        # json.loads fails with "Safety reviewer returned unparseable response".
        # Some compatible gateways ignore / reject strict json_schema — still send
        # for first-party OpenAI / Azure; others may fall back to prose.
        if schema:
            body['response_format'] = {
                'type': 'json_schema',
                'json_schema': {
                    'name': 'odoo_ai_response',
                    'strict': True,
                    'schema': normalize_openai_strict_schema(schema),
                },
            }

        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/chat/completions')
        response = http_json('OpenAI', 'POST', url, headers, body)
        choices = response.get('choices') or []
        if not choices:
            raise UserError('OpenAI API returned no choices.')
        message = (choices[0].get('message') or {})
        assistant = _openai_message_to_odoo(message)
        if schema:
            assistant = coerce_schema_text_parts(assistant)
        return completion_response(assistant)


class OpenAIEmbeddingProvider:
    """Embeddings via OpenAI Embeddings API (fixed 1536 dims for Odoo Vector)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        gateway: str = 'openai',
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_EMBEDDING_MODEL
        self.gateway = gateway or 'openai'
        self.base_url = _normalize_openai_base_url(
            base_url or DEFAULT_BASE_URL, gateway=self.gateway,
        )
        self.dimensions = dimensions

    def embed(self, inputs: list, model: str | None = None, mode: str | None = None):
        """Return ``{'embeddings': [[float, ...], ...]}`` matching Odoo IAP shape.

        ``mode`` (document/query) is accepted for API parity with IAP but unused;
        text-embedding-3 models do not require a separate query/document endpoint.
        """
        del mode  # unused — kept for call-site compatibility
        if not self.api_key:
            raise UserError('OpenAI API key is not configured.')
        _require_gateway_capability(self.gateway, 'embedding', 'Embeddings / RAG')

        texts = [format_embedding_input(item) for item in (inputs or [])]
        if not texts:
            return {'embeddings': []}

        api_model = (model or self.model or DEFAULT_EMBEDDING_MODEL).strip()
        if _is_openrouter(self.gateway):
            api_model = _openrouter_model(api_model)
        _logger.debug(
            'OpenAI embed gateway=%s model=%s inputs=%s dimensions=%s base_url=%s',
            self.gateway, api_model, len(texts), self.dimensions, self.base_url,
        )
        body: dict[str, Any] = {
            'model': api_model,
            'input': texts,
        }
        # text-embedding-3-* supports dimensions; ada-002 is already 1536.
        if _embedding_model_supports_dimensions(api_model):
            body['dimensions'] = int(self.dimensions)

        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/embeddings')
        response = http_json('OpenAI', 'POST', url, headers, body)
        data = response.get('data') or []
        if len(data) != len(texts):
            raise UserError(
                f'OpenAI embeddings returned {len(data)} vectors for {len(texts)} inputs.'
            )
        # API may return items out of order; sort by index.
        ordered = sorted(data, key=lambda row: row.get('index', 0))
        vectors = []
        for row in ordered:
            vector = row.get('embedding')
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                got = len(vector) if isinstance(vector, list) else type(vector).__name__
                raise UserError(
                    f'OpenAI embedding dimension mismatch: expected {self.dimensions}, got {got}.'
                )
            vectors.append(vector)
        return {'embeddings': vectors}


def _realtime_transcription_config(
    model: str,
    *,
    language: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Build ``audio.input.transcription`` for a Realtime transcription session."""
    cfg: dict[str, Any] = {'model': model}
    lang = (language or '').strip()
    if lang:
        if model in _REALTIME_LANGUAGES_MODELS or model.startswith('gpt-live'):
            cfg['languages'] = [lang]
        else:
            cfg['language'] = lang
    text_prompt = (prompt or '').strip()
    if text_prompt:
        cfg['prompt'] = text_prompt
    return cfg


class OpenAITranscriptionProvider:
    """Batch + realtime speech-to-text via OpenAI Audio / Realtime APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_STT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        realtime_model: str = DEFAULT_REALTIME_STT_MODEL,
        gateway: str = 'openai',
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_STT_MODEL
        self.realtime_model = realtime_model or DEFAULT_REALTIME_STT_MODEL
        self.gateway = gateway or 'openai'
        self.base_url = _normalize_openai_base_url(
            base_url or DEFAULT_BASE_URL, gateway=self.gateway,
        )

    def create_realtime_session(
        self,
        *,
        language: str | None = None,
        prompt: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Mint an ephemeral Realtime transcription client secret.

        Returns ``{'session_token': str, 'expires_at': int|None}`` matching the
        field names expected by Odoo's voice transcription UI.
        """
        if not self.api_key:
            raise UserError('OpenAI API key is not configured.')
        _require_gateway_capability(self.gateway, 'stt', 'Speech-to-text')
        if _is_openrouter(self.gateway):
            raise UserError(
                'OpenRouter speech-to-text supports batch transcription only. '
                'Use OpenAI, Azure, or Odoo AI (IAP) for live browser STT.'
            )

        api_model = (model or self.realtime_model or DEFAULT_REALTIME_STT_MODEL).strip()
        transcription = _realtime_transcription_config(
            api_model, language=language, prompt=prompt,
        )
        body: dict[str, Any] = {
            'expires_after': {
                'anchor': 'created_at',
                'seconds': 600,
            },
            'session': {
                'type': 'transcription',
                'audio': {
                    'input': {
                        'format': {
                            'type': 'audio/pcm',
                            'rate': 24000,
                        },
                        'transcription': transcription,
                        'turn_detection': None,
                    },
                },
            },
        }
        _logger.debug(
            'OpenAI realtime STT session gateway=%s model=%s language=%s prompt_len=%s',
            self.gateway, api_model, language, len(prompt or ''),
        )
        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/realtime/client_secrets')
        payload = http_json('OpenAI', 'POST', url, headers, body, timeout=60)
        token = (payload or {}).get('value')
        if not token:
            # Legacy transcription_sessions shape fallback.
            client_secret = (payload or {}).get('client_secret') or {}
            token = client_secret.get('value')
        if not token:
            raise UserError('OpenAI realtime transcription session did not return a client secret.')
        expires_at = (payload or {}).get('expires_at')
        if expires_at is None:
            client_secret = (payload or {}).get('client_secret') or {}
            expires_at = client_secret.get('expires_at')
        return {
            'session_token': token,
            'expires_at': expires_at,
            'model': api_model,
        }

    def transcribe(
        self,
        audio_base64: str,
        *,
        mimetype: str = 'audio/mp3',
        language: str | None = None,
        response_format: str = 'text',
        model: str | None = None,
    ) -> dict:
        """Return ``{'text': str}`` matching Odoo IAP transcription shape."""
        if not self.api_key:
            raise UserError('OpenAI API key is not configured.')
        _require_gateway_capability(self.gateway, 'stt', 'Speech-to-text')
        audio_bytes = decode_transcription_audio(audio_base64)

        api_model = (model or self.model or DEFAULT_STT_MODEL).strip()
        fmt = (response_format or 'text').strip()
        if _is_openrouter(self.gateway):
            return self._transcribe_openrouter(
                audio_base64,
                audio_bytes=audio_bytes,
                mimetype=mimetype,
                language=language,
                response_format=fmt,
                model=api_model,
            )

        _logger.debug(
            'OpenAI transcribe gateway=%s model=%s format=%s language=%s bytes=%s mimetype=%s',
            self.gateway, api_model, fmt, language, len(audio_bytes), mimetype,
        )
        fields = {
            'model': api_model,
            'response_format': fmt,
        }
        if language:
            fields['language'] = language

        filename = f'audio.{_mimetype_to_extension(mimetype)}'
        content_type = sanitize_mimetype(mimetype)
        boundary = f'----ciAiOpenAI{uuid.uuid4().hex}'
        url = build_api_url(self.base_url, '/v1/audio/transcriptions')
        raw = http_multipart_post(
            'OpenAI',
            url,
            headers={'authorization': f'Bearer {self.api_key}'},
            fields=fields,
            files=[('file', filename, content_type, audio_bytes)],
            boundary=boundary,
            timeout=180,
        )
        if fmt in ('json', 'verbose_json'):
            payload = json.loads(raw.decode('utf-8') if raw else '{}')
            text = payload.get('text') or ''
        else:
            text = raw.decode('utf-8') if raw else ''
        return {'text': text}

    def _transcribe_openrouter(
        self,
        audio_base64: str,
        *,
        audio_bytes: bytes,
        mimetype: str,
        language: str | None,
        response_format: str,
        model: str,
    ) -> dict:
        """Batch STT via OpenRouter JSON ``input_audio`` (no text/vtt/srt)."""
        del audio_base64  # validated via audio_bytes; re-encode cleanly for OpenRouter
        api_model = _openrouter_model(model or DEFAULT_STT_MODEL)
        want_vtt = response_format == 'vtt'
        # OpenRouter rejects text/srt/vtt; coerce to supported JSON shapes.
        if want_vtt or response_format in ('srt',):
            api_format = 'verbose_json'
        elif response_format in ('json', 'verbose_json'):
            api_format = response_format
        else:
            api_format = 'json'

        clean_b64 = base64.b64encode(audio_bytes).decode('ascii')
        audio_format = _mimetype_to_extension(mimetype)
        body: dict[str, Any] = {
            'model': api_model,
            'input_audio': {
                'data': clean_b64,
                'format': audio_format,
            },
            'response_format': api_format,
        }
        if language:
            body['language'] = language

        _logger.debug(
            'OpenRouter transcribe model=%s format=%s->%s language=%s mimetype=%s payload_chars=%s',
            api_model, response_format, api_format, language, mimetype, len(clean_b64),
        )
        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/audio/transcriptions')
        payload = http_json('OpenAI', 'POST', url, headers, body, timeout=180) or {}
        if want_vtt:
            return {'text': _verbose_json_to_webvtt(payload)}
        return {'text': payload.get('text') or ''}


class OpenAIImageProvider:
    """Image generation via OpenAI Images API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_IMAGE_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        gateway: str = 'openai',
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_IMAGE_MODEL
        self.gateway = gateway or 'openai'
        self.base_url = _normalize_openai_base_url(
            base_url or DEFAULT_BASE_URL, gateway=self.gateway,
        )

    def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = '1:1',
        model: str | None = None,
        n: int = 1,
    ) -> list[dict]:
        """Return Odoo ``inline_data`` message parts (base64 + mimetype)."""
        if not self.api_key:
            raise UserError('OpenAI API key is not configured.')
        _require_gateway_capability(self.gateway, 'image', 'Image generation')
        if not (prompt or '').strip():
            raise UserError('Image prompt is required.')

        api_model = (model or self.model or DEFAULT_IMAGE_MODEL).strip()
        if _is_openrouter(self.gateway):
            return self._generate_openrouter(
                prompt.strip(),
                aspect_ratio=aspect_ratio,
                model=api_model,
                n=n,
            )

        size = _aspect_ratio_to_size(aspect_ratio, api_model)
        _logger.debug(
            'OpenAI image generate gateway=%s model=%s size=%s n=%s prompt_len=%s',
            self.gateway, api_model, size, n, len(prompt or ''),
        )
        body: dict[str, Any] = {
            'model': api_model,
            'prompt': prompt.strip(),
            'n': max(1, min(int(n or 1), 4)),
            'size': size,
        }
        # dall-e-2/3 accept response_format; gpt-image-* returns b64 by default.
        if api_model.startswith('dall-e'):
            body['response_format'] = 'b64_json'

        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/images/generations')
        response = http_json('OpenAI', 'POST', url, headers, body, timeout=180)
        return self._image_response_parts(response)

    def _generate_openrouter(
        self,
        prompt: str,
        *,
        aspect_ratio: str,
        model: str,
        n: int,
    ) -> list[dict]:
        """Image generation via OpenRouter ``POST /v1/images``."""
        api_model = _openrouter_model(model or DEFAULT_IMAGE_MODEL)
        ratio = (aspect_ratio or '1:1').strip() or '1:1'
        body: dict[str, Any] = {
            'model': api_model,
            'prompt': prompt,
            'n': max(1, min(int(n or 1), 4)),
            'aspect_ratio': ratio,
            'output_format': 'png',
        }
        _logger.debug(
            'OpenRouter image generate model=%s aspect_ratio=%s n=%s prompt_len=%s',
            api_model, ratio, body['n'], len(prompt),
        )
        headers = _openai_auth_headers(self.api_key, self.base_url)
        url = build_api_url(self.base_url, '/v1/images')
        response = http_json('OpenAI', 'POST', url, headers, body, timeout=180)
        return self._image_response_parts(response)

    @staticmethod
    def _image_response_parts(response: dict[str, Any] | None) -> list[dict]:
        parts: list[dict] = []
        for row in (response or {}).get('data') or []:
            b64 = row.get('b64_json')
            if not b64 and row.get('url'):
                raise UserError(
                    'OpenAI returned an image URL instead of base64. '
                    'Configure the model to return b64_json.'
                )
            if not b64:
                continue
            parts.append({
                'type': 'inline_data',
                'data': b64,
                'mimetype': row.get('media_type') or 'image/png',
            })
        if not parts:
            raise UserError('OpenAI Images API returned no image data.')
        return parts
