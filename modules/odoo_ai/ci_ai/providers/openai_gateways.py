# Part of ci_ai.

"""OpenAI-compatible gateway presets (v1.11).

Chat Completions hosts share the OpenAI adapter. Embeddings / STT / image stay
limited to first-party OpenAI and Azure unless a later release widens support.
"""

from __future__ import annotations

from typing import Any

# Capabilities the OpenAI adapter may safely route for a given gateway.
_FULL = frozenset({'chat', 'embedding', 'stt', 'image'})
_CHAT_ONLY = frozenset({'chat'})
_CHAT_EMBED = frozenset({'chat', 'embedding'})

OPENAI_GATEWAY_SELECTION = [
    ('openai', 'OpenAI'),
    ('deepseek', 'DeepSeek'),
    ('groq', 'Groq'),
    ('openrouter', 'OpenRouter'),
    ('azure', 'Azure OpenAI'),
    ('ollama', 'Ollama (local)'),
    ('custom', 'Custom (OpenAI-compatible)'),
]

# Public HTTPS hosts allowed for OpenAI-compatible traffic (exact match).
OPENAI_COMPAT_PUBLIC_HOSTS = frozenset({
    'api.openai.com',
    'api.deepseek.com',
    'api.groq.com',
    'openrouter.ai',
})

OPENAI_GATEWAY_PRESETS: dict[str, dict[str, Any]] = {
    'openai': {
        'base_url': 'https://api.openai.com',
        'default_chat_model': 'gpt-4o',
        'capabilities': _FULL,
        'allow_path': False,
        'allow_loopback': False,
    },
    'deepseek': {
        'base_url': 'https://api.deepseek.com',
        'default_chat_model': 'deepseek-chat',
        'capabilities': _CHAT_ONLY,
        'allow_path': False,
        'allow_loopback': False,
    },
    'groq': {
        # Groq OpenAI-compat lives under /openai/v1/...
        'base_url': 'https://api.groq.com/openai',
        'default_chat_model': 'llama-3.3-70b-versatile',
        'capabilities': _CHAT_ONLY,
        'allow_path': True,
        'allow_loopback': False,
    },
    'openrouter': {
        'base_url': 'https://openrouter.ai/api',
        'default_chat_model': 'openai/gpt-4o-mini',
        'capabilities': _CHAT_ONLY,
        'allow_path': True,
        'allow_loopback': False,
    },
    'azure': {
        # Resource-specific host; admin must set openai_base_url.
        'base_url': False,
        'default_chat_model': False,
        'capabilities': _FULL,
        'allow_path': True,
        'allow_loopback': False,
    },
    'ollama': {
        # Adapter appends /v1/chat/completions → http://127.0.0.1:11434/v1/...
        'base_url': 'http://127.0.0.1:11434',
        'default_chat_model': 'llama3.2',
        # Local Ollama exposes /v1/embeddings; STT/image are not supported.
        'capabilities': _CHAT_EMBED,
        'allow_path': False,
        'allow_loopback': True,
    },
    'custom': {
        'base_url': False,
        'default_chat_model': False,
        'capabilities': _CHAT_ONLY,
        'allow_path': True,
        'allow_loopback': False,
    },
}


def get_gateway_preset(gateway: str | None) -> dict[str, Any]:
    return OPENAI_GATEWAY_PRESETS.get(gateway or 'openai') or OPENAI_GATEWAY_PRESETS['openai']


def gateway_supports(gateway: str | None, capability: str) -> bool:
    return capability in get_gateway_preset(gateway)['capabilities']


def resolve_gateway_base_url(gateway: str | None, configured_url: str | None) -> str:
    """Return the effective base URL for a gateway + optional override.

    Named SaaS presets always use the built-in host (ignore stale base_url).
    Azure / custom / Ollama use the configured URL (with preset default).
    """
    preset = get_gateway_preset(gateway)
    configured = (configured_url or '').strip()
    if gateway in ('azure', 'custom', 'ollama'):
        return configured or (preset.get('base_url') or 'https://api.openai.com')
    return preset.get('base_url') or 'https://api.openai.com'
