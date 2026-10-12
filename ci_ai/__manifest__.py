# Part of ci_ai. Bring-your-own AI backends for Odoo Enterprise AI.
{
    'name': 'Odoo AI: bring your own provider',
    'category': 'Productivity',
    'version': '20.0.1.12.0',
    'summary': 'Use Odoo AI but with your own provider',
    'description': """
Odoo AI: bring your own provider — use Odoo AI but with your own Anthropic, OpenAI, or Gemini keys.

Configure per-capability providers under Settings > AI.

Chat: Odoo AI (IAP), Anthropic, OpenAI / Compatible, Google Gemini.
Embeddings / RAG: IAP, OpenAI, Azure, OpenRouter, Ollama, Google (1536-dim).
Speech-to-text: IAP, OpenAI / Azure (batch + realtime), OpenRouter (batch), Google (batch).
Image generation: IAP, OpenAI / Azure, OpenRouter, Google.

OpenAI-compatible gateways: OpenAI, DeepSeek, Groq, OpenRouter, Azure, Ollama, custom.
v1.12: OpenRouter embeddings, batch STT, and image generation (no realtime STT).
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
        'static/description/banner.png',
        'static/description/main_screenshot.png',
    ],
    'installable': True,
    'application': False,
}
