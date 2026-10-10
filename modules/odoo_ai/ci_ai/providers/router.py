# Part of ci_ai.

"""Resolve chat / embedding / STT / image providers from ci.ai.provider.config."""

from __future__ import annotations

from odoo.exceptions import UserError

from .anthropic_provider import AnthropicChatProvider
from .google_provider import (
    DEFAULT_CHAT_MODEL as GOOGLE_DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL as GOOGLE_DEFAULT_EMBEDDING_MODEL,
    DEFAULT_IMAGE_MODEL as GOOGLE_DEFAULT_IMAGE_MODEL,
    DEFAULT_STT_MODEL as GOOGLE_DEFAULT_STT_MODEL,
    GoogleChatProvider,
    GoogleEmbeddingProvider,
    GoogleImageProvider,
    GoogleTranscriptionProvider,
)
from .openai_gateways import gateway_supports, resolve_gateway_base_url
from .openai_provider import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_REALTIME_STT_MODEL,
    DEFAULT_STT_MODEL,
    OpenAIChatProvider,
    OpenAIEmbeddingProvider,
    OpenAIImageProvider,
    OpenAITranscriptionProvider,
)


def _openai_gateway(config) -> str:
    return getattr(config, 'openai_gateway', None) or 'openai'


def _openai_base_url(config) -> str:
    return resolve_gateway_base_url(
        _openai_gateway(config),
        config.openai_base_url,
    )


def _assert_openai_capability(env, config, capability: str, label: str) -> None:
    if gateway_supports(_openai_gateway(config), capability):
        return
    raise UserError(env._(
        'The selected OpenAI-compatible gateway does not support %(capability)s. '
        'Route %(capability)s to Odoo AI (IAP), Google, or first-party OpenAI / Azure, '
        'or change the OpenAI gateway preset.',
        capability=label,
    ))


def get_config(env):
    return env['ci.ai.provider.config'].get_solo()


def get_chat_provider_name(env) -> str:
    return get_config(env).chat_provider or 'iap'


def get_chat_provider(env):
    """Return a chat provider instance, or None when using Odoo IAP."""
    config = get_config(env)
    name = config.chat_provider or 'iap'
    if name == 'iap':
        return None
    if name == 'anthropic':
        return AnthropicChatProvider(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
            base_url=config.anthropic_base_url or 'https://api.anthropic.com',
        )
    if name == 'openai':
        _assert_openai_capability(env, config, 'chat', env._('Chat'))
        return OpenAIChatProvider(
            api_key=config.openai_api_key,
            model=config.openai_model,
            base_url=_openai_base_url(config),
            gateway=_openai_gateway(config),
        )
    if name == 'google':
        return GoogleChatProvider(
            api_key=config.google_api_key,
            model=config.google_model or GOOGLE_DEFAULT_CHAT_MODEL,
            base_url=config.google_base_url or 'https://generativelanguage.googleapis.com',
        )
    raise UserError(env._('Unknown chat provider: %s', name))


def get_embedding_provider_name(env) -> str:
    return get_config(env).embedding_provider or 'iap'


def get_embedding_provider(env):
    """Return an embedding provider instance, or None when using Odoo IAP."""
    config = get_config(env)
    name = config.embedding_provider or 'iap'
    if name == 'iap':
        return None
    if name == 'openai':
        _assert_openai_capability(env, config, 'embedding', env._('Embeddings / RAG'))
        return OpenAIEmbeddingProvider(
            api_key=config.openai_api_key,
            model=config.openai_embedding_model or DEFAULT_EMBEDDING_MODEL,
            base_url=_openai_base_url(config),
            gateway=_openai_gateway(config),
        )
    if name == 'google':
        return GoogleEmbeddingProvider(
            api_key=config.google_api_key,
            model=config.google_embedding_model or GOOGLE_DEFAULT_EMBEDDING_MODEL,
            base_url=config.google_base_url or 'https://generativelanguage.googleapis.com',
        )
    raise UserError(env._('Unknown embedding provider: %s', name))


def get_stt_provider_name(env) -> str:
    return get_config(env).stt_provider or 'iap'


def get_stt_provider(env):
    """Return an STT provider instance, or None when using Odoo IAP."""
    config = get_config(env)
    name = config.stt_provider or 'iap'
    if name == 'iap':
        return None
    if name == 'openai':
        _assert_openai_capability(env, config, 'stt', env._('Speech-to-text'))
        return OpenAITranscriptionProvider(
            api_key=config.openai_api_key,
            model=config.openai_stt_model or DEFAULT_STT_MODEL,
            realtime_model=config.openai_realtime_stt_model or DEFAULT_REALTIME_STT_MODEL,
            base_url=_openai_base_url(config),
            gateway=_openai_gateway(config),
        )
    if name == 'google':
        return GoogleTranscriptionProvider(
            api_key=config.google_api_key,
            model=config.google_stt_model or GOOGLE_DEFAULT_STT_MODEL,
            base_url=config.google_base_url or 'https://generativelanguage.googleapis.com',
        )
    raise UserError(env._('Unknown speech-to-text provider: %s', name))


def get_image_provider_name(env) -> str:
    return get_config(env).image_provider or 'iap'


def get_image_provider(env):
    """Return an image provider instance, or None when using Odoo IAP."""
    config = get_config(env)
    name = config.image_provider or 'iap'
    if name == 'iap':
        return None
    if name == 'openai':
        _assert_openai_capability(env, config, 'image', env._('Image generation'))
        return OpenAIImageProvider(
            api_key=config.openai_api_key,
            model=config.openai_image_model or DEFAULT_IMAGE_MODEL,
            base_url=_openai_base_url(config),
            gateway=_openai_gateway(config),
        )
    if name == 'google':
        return GoogleImageProvider(
            api_key=config.google_api_key,
            model=config.google_image_model or GOOGLE_DEFAULT_IMAGE_MODEL,
            base_url=config.google_base_url or 'https://generativelanguage.googleapis.com',
        )
    raise UserError(env._('Unknown image provider: %s', name))
