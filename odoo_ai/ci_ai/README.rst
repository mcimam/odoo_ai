# CI AI Providers (`ci_ai`)

Route Odoo Enterprise AI capabilities through Odoo IAP, Anthropic, OpenAI-compatible gateways, or Google Gemini.

## Install

1. Add this folder to the Odoo addons path (alongside Enterprise `ai_agentic`).
2. Update apps list and install **CI AI Providers**.
3. Open **Settings → AI**.

## Configuration

| Capability | Providers (v1.11) |
|------------|------------------|
| Chat | Odoo AI (IAP), Anthropic, OpenAI / Compatible, Google Gemini |
| Embeddings / RAG | Odoo AI (IAP), OpenAI / Azure / Ollama (`text-embedding-3-small` @ 1536 for OpenAI), Google (`gemini-embedding-001` @ 1536) |
| Speech-to-text | Odoo AI (IAP), OpenAI / Azure (Whisper batch + `gpt-live-transcribe` realtime), Google (Gemini multimodal batch) |
| Image generation | Odoo AI (IAP), OpenAI / Azure Images (`dall-e-3`), Google Gemini image (`gemini-2.5-flash-image`) |

Enable Anthropic / OpenAI / Google with the checkboxes, then fill API keys. Select providers under Capability routing.

### OpenAI-compatible gateways (v1.11)

Under **OpenAI / Compatible**, pick a gateway preset:

| Gateway | Chat | Embeddings | STT | Image | Base URL |
|---------|------|------------|-----|-------|----------|
| OpenAI | ✓ | ✓ | ✓ | ✓ | fixed `api.openai.com` |
| DeepSeek | ✓ | — | — | — | fixed |
| Groq | ✓ | — | — | — | fixed |
| OpenRouter | ✓ | — | — | — | fixed |
| Azure OpenAI | ✓* | ✓* | ✓* | ✓* | admin-set `*.openai.azure.com` |
| Ollama (local) | ✓ | ✓* | — | — | `http://127.0.0.1:11434` (editable) |
| Custom | ✓ | — | — | — | allowlisted HTTPS host |

\*Ollama embeddings must still produce **1536**-dimensional vectors for Odoo RAG.

\*Azure: the adapter calls standard `/v1/...` paths. Use a resource that exposes OpenAI-compatible `/v1` (or a gateway in front of Azure). Classic Azure “deployments + api-version” URLs are not rewritten yet.

When Speech-to-text is OpenAI:
- **Batch** (composer voice message, call recordings) uses the Whisper model (`whisper-1` by default).
- **Live** browser STT mints an ephemeral Realtime client secret for `gpt-live-transcribe` (configurable).

When Speech-to-text is Google:
- **Batch** uses Gemini multimodal `generateContent` with the configured STT model.
- **Live** browser STT is not supported yet (use OpenAI or IAP).

Google auth uses an AI Studio API key (`x-goog-api-key`). Vertex / service accounts are reserved for a later patch.

System admins only.

## Roadmap

| Version | Provider | Capabilities |
|---------|----------|--------------|
| **v1.0** | IAP, Cursor, Anthropic | Chat BYO |
| **v1.1** | OpenAI | Chat + tools |
| **v1.2** | OpenAI | Embeddings (1536) |
| **v1.3** | OpenAI | STT (batch) |
| **v1.4** | OpenAI | Image generation |
| **v1.5** | OpenAI | Realtime STT (`gpt-live-transcribe`) |
| **v1.6** | Google | Chat + tools |
| **v1.7** | Google | Embeddings (1536) |
| **v1.8** | Google | STT (batch) |
| **v1.9** | Google | Image generation |
| **v1.11** (current) | OpenAI-compatible | Multi-gateway (DeepSeek, Groq, OpenRouter, Azure, Ollama, custom) |
| **v1.12** (planned) | OpenCode Zen | First-class Zen API key + chat models |

Details: [`.agent/docs/roadmap-ci-ai-openai-google.md`](../../../.agent/docs/roadmap-ci-ai-openai-google.md).

## Docs

- [PRD](../../../.agent/docs/prd-ci-ai.md)
- [Provider roadmap](../../../.agent/docs/roadmap-ci-ai-openai-google.md)
