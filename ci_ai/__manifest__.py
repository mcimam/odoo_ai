# Part of ci_ai. Custom AI providers for Odoo Enterprise AI.
{
    'name': 'CI AI Providers',
    'category': 'Productivity',
    'version': '20.0.1.11.1',
    'summary': 'Route Odoo AI capabilities to Odoo IAP, Anthropic, OpenAI-compatible, or Google',
    'description': """
Configure per-capability AI providers under Settings > AI.
v1.11: OpenAI-compatible gateways (DeepSeek, Groq, OpenRouter, Azure, Ollama, custom).
v1.11.1: Security/guideline hardening (SSRF redirects, exceptions, XML id).
Chat: IAP, Anthropic, OpenAI/compatible, Google. Embeddings / STT / image: IAP, OpenAI/Azure, Google (Ollama embeddings).
    """,
    'depends': ['ai_agentic', 'base_setup'],
    'data': [
        'security/ir.access.csv',
        'data/ci_ai_provider_config_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'ai/static/src/discuss/core/common/ai_session_model.js',
                'ci_ai/static/src/discuss/core/common/ai_session_model_patch.js',
            ),
            (
                'after',
                'ai/static/src/discuss/core/common/thread_model_patch.js',
                'ci_ai/static/src/discuss/core/common/thread_model_patch.js',
            ),
            (
                'after',
                'ai/static/src/core/realtime_client.js',
                'ci_ai/static/src/core/realtime_client_patch.js',
            ),
            (
                'after',
                'ai/static/src/editor/embedded_components/core/voice_transcription.js',
                'ci_ai/static/src/editor/voice_transcription_patch.js',
            ),
        ],
    },
    'author': 'CI',
    'license': 'LGPL-3',
    'images': [
        'static/description/main_screenshot.png',
    ],
    'installable': True,
    'application': False,
}
