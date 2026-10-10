# Part of ci_ai.

"""Google Gemini adapters: chat, embeddings (1536), batch STT, and image generation."""

from __future__ import annotations

import logging
import re
from typing import Any

from odoo.exceptions import UserError, ValidationError

from .base import coerce_schema_text_parts, completion_response, format_embedding_input
from .http_security import (
    ProviderHttpError,
    build_api_url,
    decode_transcription_audio,
    http_json,
    is_allowed_google_host,
    sanitize_mimetype,
    validate_https_base_url,
)

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com'
DEFAULT_CHAT_MODEL = 'gemini-2.5-flash'
DEFAULT_EMBEDDING_MODEL = 'gemini-embedding-001'
DEFAULT_STT_MODEL = 'gemini-2.5-flash'
DEFAULT_IMAGE_MODEL = 'gemini-2.5-flash-image'
EMBEDDING_DIMENSIONS = 1536


def _normalize_google_base_url(base_url: str) -> str:
    try:
        return validate_https_base_url(
            base_url,
            default_url=DEFAULT_BASE_URL,
            host_allowed=is_allowed_google_host,
            field_label='Google Base URL',
        )
    except ValidationError as err:
        raise UserError(str(err)) from err


def _google_headers(api_key: str) -> dict[str, str]:
    return {
        'content-type': 'application/json',
        'x-goog-api-key': api_key,
    }


_SAFE_MODEL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$')


def _model_path(model: str) -> str:
    model = (model or '').strip()
    if model.startswith('models/'):
        model_id = model[len('models/'):]
    else:
        model_id = model
    if not model_id or not _SAFE_MODEL_ID.match(model_id) or '..' in model_id:
        raise UserError('Google model id contains invalid characters.')
    return f'models/{model_id}'


def _odoo_tools_to_google(tools: list[dict] | None) -> list[dict]:
    declarations = []
    for tool in tools or []:
        schema = tool.get('schema') or {'type': 'object', 'properties': {}, 'required': []}
        declarations.append({
            'name': tool['name'],
            'description': tool.get('instructions') or tool['name'],
            'parameters': schema,
        })
    if not declarations:
        return []
    return [{'functionDeclarations': declarations}]


def _odoo_messages_to_google(messages: list[dict]) -> list[dict]:
    """Map Odoo chat messages to Gemini ``contents`` (roles: user / model)."""
    out: list[dict] = []
    for msg in messages or []:
        role = msg.get('role')
        if role == 'assistant':
            parts: list[Any] = []
            for part in msg.get('content') or []:
                ptype = part.get('type')
                if ptype == 'text':
                    parts.append({'text': part.get('text') or ''})
                elif ptype == 'tool_call':
                    call: dict[str, Any] = {
                        'name': part.get('name'),
                        'args': part.get('args') or {},
                    }
                    if part.get('call_id'):
                        call['id'] = str(part['call_id'])
                    parts.append({'functionCall': call})
            if parts:
                out.append({'role': 'model', 'parts': parts})
        elif role == 'user':
            parts = []
            for part in msg.get('content') or []:
                ptype = part.get('type')
                if ptype == 'text':
                    parts.append({'text': part.get('text') or ''})
                elif ptype == 'tool_result':
                    response_payload = part.get('result')
                    if not isinstance(response_payload, dict):
                        response_payload = {'result': response_payload}
                    fr: dict[str, Any] = {
                        'name': part.get('tool_name') or '',
                        'response': {
                            **response_payload,
                            'success': part.get('success', True),
                        },
                    }
                    if part.get('tool_call_id'):
                        fr['id'] = str(part['tool_call_id'])
                    parts.append({'functionResponse': fr})
                elif ptype == 'inline_data':
                    parts.append({'text': '[inline attachment omitted]'})
            if parts:
                out.append({'role': 'user', 'parts': parts})
    return out


def _google_candidate_to_odoo(candidate: dict) -> dict:
    content = (candidate or {}).get('content') or {}
    parts: list[dict] = []
    for block in content.get('parts') or []:
        if 'text' in block and block.get('text') is not None:
            if block.get('thought') and not (block.get('text') or '').strip():
                continue
            parts.append({'type': 'text', 'text': block.get('text') or ''})
        elif 'functionCall' in block:
            call = block.get('functionCall') or {}
            parts.append({
                'type': 'tool_call',
                'name': call.get('name'),
                'args': call.get('args') or {},
                'call_id': call.get('id') or call.get('name'),
            })
    if not parts:
        parts = [{'type': 'text', 'text': ''}]
    return {'role': 'assistant', 'content': parts, 'provider_metadata': {}}


def _aspect_ratio_for_google(aspect_ratio: str | None) -> str:
    ratio = (aspect_ratio or '1:1').strip()
    allowed = {
        '1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9',
    }
    return ratio if ratio in allowed else '1:1'


class GoogleChatProvider:
    """Chat via Gemini ``models.generateContent`` with function calling."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_CHAT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_CHAT_MODEL
        self.base_url = _normalize_google_base_url(base_url or DEFAULT_BASE_URL)

    def complete(self, messages, instructions, tools=None, **options):
        if not self.api_key:
            raise UserError('Google API key is not configured.')

        schema = options.get('schema')
        _logger.debug(
            'Google chat complete model=%s base_url=%s messages=%s tools=%s schema=%s',
            self.model, self.base_url, len(messages or []), len(tools or []), bool(schema),
        )
        body: dict[str, Any] = {
            'contents': _odoo_messages_to_google(messages),
        }
        if instructions:
            body['systemInstruction'] = {
                'parts': [{'text': instructions}],
            }
        google_tools = _odoo_tools_to_google(tools)
        if google_tools:
            body['tools'] = google_tools

        generation_config: dict[str, Any] = {}
        max_tokens = options.get('max_tokens')
        if max_tokens:
            generation_config['maxOutputTokens'] = int(max_tokens)
        if schema:
            generation_config['responseMimeType'] = 'application/json'
            generation_config['responseSchema'] = schema
        if generation_config:
            body['generationConfig'] = generation_config

        url = build_api_url(
            self.base_url,
            f'/v1beta/{_model_path(self.model)}:generateContent',
        )
        response = http_json(
            'Google', 'POST', url, _google_headers(self.api_key), body, timeout=180,
        )
        candidates = response.get('candidates') or []
        if not candidates:
            raise UserError('Google Gemini API returned no candidates.')
        assistant = _google_candidate_to_odoo(candidates[0])
        if schema:
            assistant = coerce_schema_text_parts(assistant)
        return completion_response(assistant)


class GoogleEmbeddingProvider:
    """Embeddings via Gemini ``embedContent`` with ``outputDimensionality=1536``."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_EMBEDDING_MODEL
        self.base_url = _normalize_google_base_url(base_url or DEFAULT_BASE_URL)
        self.dimensions = dimensions

    def embed(self, inputs: list, model: str | None = None, mode: str | None = None):
        del mode  # Gemini taskType optional; unused for Odoo parity
        if not self.api_key:
            raise UserError('Google API key is not configured.')

        texts = [format_embedding_input(item) for item in (inputs or [])]
        if not texts:
            return {'embeddings': []}

        api_model = (model or self.model or DEFAULT_EMBEDDING_MODEL).strip()
        _logger.debug(
            'Google embed model=%s inputs=%s dimensions=%s base_url=%s',
            api_model, len(texts), self.dimensions, self.base_url,
        )

        if len(texts) > 1:
            vectors = self._batch_embed(api_model, texts)
        else:
            vectors = [self._single_embed(api_model, texts[0])]

        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                got = len(vector) if isinstance(vector, list) else type(vector).__name__
                raise UserError(
                    f'Google embedding dimension mismatch: expected {self.dimensions}, got {got}.'
                )
        return {'embeddings': vectors}

    def _single_embed(self, api_model: str, text: str) -> list[float]:
        body = {
            'content': {'parts': [{'text': text}]},
            'outputDimensionality': int(self.dimensions),
        }
        url = build_api_url(
            self.base_url,
            f'/v1beta/{_model_path(api_model)}:embedContent',
        )
        response = http_json(
            'Google', 'POST', url, _google_headers(self.api_key), body, timeout=120,
        )
        return ((response.get('embedding') or {}).get('values')) or []

    def _batch_embed(self, api_model: str, texts: list[str]) -> list[list[float]]:
        body = {
            'requests': [{
                'model': _model_path(api_model),
                'content': {'parts': [{'text': text}]},
                'outputDimensionality': int(self.dimensions),
            } for text in texts],
        }
        url = build_api_url(
            self.base_url,
            f'/v1beta/{_model_path(api_model)}:batchEmbedContents',
        )
        try:
            response = http_json(
                'Google', 'POST', url, _google_headers(self.api_key), body, timeout=180,
            )
        except ProviderHttpError as err:
            # Only fall back when the batch endpoint is missing/unavailable.
            if err.status_code not in (404, 405, 501):
                raise
            _logger.info(
                'Google batch embeddings unavailable (HTTP %s); falling back to singles',
                err.status_code,
            )
            return [self._single_embed(api_model, text) for text in texts]

        embeddings = response.get('embeddings') or []
        if len(embeddings) != len(texts):
            raise UserError(
                f'Google embeddings returned {len(embeddings)} vectors for {len(texts)} inputs.'
            )
        return [row.get('values') or [] for row in embeddings]


class GoogleTranscriptionProvider:
    """Batch STT via Gemini multimodal ``generateContent`` (AI Studio API key)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_STT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_STT_MODEL
        self.base_url = _normalize_google_base_url(base_url or DEFAULT_BASE_URL)

    def transcribe(
        self,
        audio_base64: str,
        *,
        mimetype: str = 'audio/mp3',
        language: str | None = None,
        response_format: str = 'text',
        model: str | None = None,
    ) -> dict:
        if not self.api_key:
            raise UserError('Google API key is not configured.')
        # Validate size/payload; Gemini still wants base64 in the JSON body.
        decode_transcription_audio(audio_base64)

        api_model = (model or self.model or DEFAULT_STT_MODEL).strip()
        fmt = (response_format or 'text').strip()
        mime = sanitize_mimetype(mimetype)
        if mime == 'application/octet-stream':
            mime = 'audio/mpeg'
        _logger.debug(
            'Google transcribe model=%s format=%s language=%s mimetype=%s payload_chars=%s',
            api_model, fmt, language, mime, len(audio_base64 or ''),
        )

        if fmt == 'vtt':
            prompt = (
                'Transcribe this audio as WebVTT. Return ONLY a valid WEBVTT document '
                'with cues. Do not add commentary.'
            )
        else:
            prompt = 'Transcribe this audio. Return ONLY the plain transcript text.'
        if language:
            prompt += f' The primary language is {language}.'

        body = {
            'contents': [{
                'role': 'user',
                'parts': [
                    {
                        'inlineData': {
                            'mimeType': mime,
                            'data': audio_base64,
                        },
                    },
                    {'text': prompt},
                ],
            }],
        }
        url = build_api_url(
            self.base_url,
            f'/v1beta/{_model_path(api_model)}:generateContent',
        )
        response = http_json(
            'Google', 'POST', url, _google_headers(self.api_key), body, timeout=180,
        )
        text_parts = []
        for candidate in response.get('candidates') or []:
            for part in ((candidate.get('content') or {}).get('parts') or []):
                if part.get('text'):
                    text_parts.append(part['text'])
        return {'text': '\n'.join(text_parts).strip()}


class GoogleImageProvider:
    """Image generation via Gemini image models (``responseModalities: IMAGE``)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_IMAGE_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = (api_key or '').strip()
        self.model = model or DEFAULT_IMAGE_MODEL
        self.base_url = _normalize_google_base_url(base_url or DEFAULT_BASE_URL)

    def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = '1:1',
        model: str | None = None,
        n: int = 1,
    ) -> list[dict]:
        if not self.api_key:
            raise UserError('Google API key is not configured.')
        if not (prompt or '').strip():
            raise UserError('Image prompt is required.')

        api_model = (model or self.model or DEFAULT_IMAGE_MODEL).strip()
        ratio = _aspect_ratio_for_google(aspect_ratio)
        count = max(1, min(int(n or 1), 4))
        _logger.debug(
            'Google image generate model=%s aspect_ratio=%s n=%s prompt_len=%s',
            api_model, ratio, count, len(prompt or ''),
        )

        parts_out: list[dict] = []
        for _ in range(count):
            body = {
                'contents': [{
                    'role': 'user',
                    'parts': [{'text': prompt.strip()}],
                }],
                'generationConfig': {
                    'responseModalities': ['TEXT', 'IMAGE'],
                    'imageConfig': {
                        'aspectRatio': ratio,
                    },
                },
            }
            url = build_api_url(
                self.base_url,
                f'/v1beta/{_model_path(api_model)}:generateContent',
            )
            response = http_json(
                'Google', 'POST', url, _google_headers(self.api_key), body, timeout=180,
            )
            found = False
            for candidate in response.get('candidates') or []:
                for part in ((candidate.get('content') or {}).get('parts') or []):
                    inline = part.get('inlineData') or part.get('inline_data') or {}
                    data = inline.get('data')
                    mime = (
                        inline.get('mimeType')
                        or inline.get('mime_type')
                        or 'image/png'
                    )
                    if data:
                        parts_out.append({
                            'type': 'inline_data',
                            'data': data,
                            'mimetype': mime,
                        })
                        found = True
            if not found:
                raise UserError('Google Gemini image generation returned no image data.')
        return parts_out
