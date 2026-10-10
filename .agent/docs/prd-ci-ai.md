# PRD: `ci_ai` — Custom AI providers for Odoo 20 Enterprise

> Status: **Approved** (2026-09-28; updated for v1.10)  
> Related: [odoo20-ai-architecture.md](./odoo20-ai-architecture.md), [odoo20-ai-bypass-iap-feasibility.md](./odoo20-ai-bypass-iap-feasibility.md)

## Summary

Module **`ci_ai`** keeps Odoo’s Enterprise AI runtime (agents, Discuss sessions, skills/tools, composers, RAG UI) and lets admins route each **capability** to **Odoo IAP**, **Anthropic**, **OpenAI**, or **Google Gemini**.

**v1.10** removes Cursor Cloud Agents chat. Current stack: Anthropic (chat-only), OpenAI and Google (chat, embeddings @ 1536, STT, image). See **[roadmap-ci-ai-openai-google.md](./roadmap-ci-ai-openai-google.md)**.

## Goals

- Path B: inherit transport methods (no monkeypatch of `call_odoo_ai`).
- Per-capability provider selection including **Odoo AI (IAP)**.
- Config under **Settings → AI** (`res.config.settings`, `base.group_system`).
- Enable checkboxes for Anthropic / OpenAI / Google; credential fields appear when enabled.
- OpenAI: chat tools, embeddings @ 1536, Whisper batch STT, Realtime live STT, Images API.
- Google: Gemini chat + tools, embeddings @ 1536, multimodal batch STT, image generation.
- Anthropic: reliable tool_use ↔ Odoo `tool_call` mapping.
- Provider failures always post an error message in Discuss (no silent end of "Thinking").
- Automated tests with mocked HTTP (no real API keys in CI).

## Roadmap

| Version | Provider | Deliverable |
|---------|----------|-------------|
| v1.1–v1.5 | OpenAI | Chat, embeddings, STT, image, realtime STT (**shipped**) |
| v1.6–v1.9 | Google | Chat, embeddings, STT, image (**shipped**) |
| v1.10 | Cleanup | Remove Cursor (**shipped**) |

Odoo IAP stays available on every capability as default/fallback.

## Non-goals

- OpenAI image *edit* from reference paths (prompt-only generation).
- Cursor / MCP-only orchestration.
- Community-only AI.
- Google Vertex service-account auth / realtime STT (later).

## Depends / location

| Item | Value |
|------|-------|
| Path | `modules/odoo_ai/ci_ai` |
| Technical name | `ci_ai` |
| Depends | `ai_agentic`, `base_setup` |

## Capability matrix

| Capability | Providers (v1.10) | Hooks |
|------------|-------------------|-------|
| Chat | `iap`, `anthropic`, `openai`, `google` | `ai.session` `_get_completions`, `_save_and_submit_request` |
| Embeddings | `iap`, `openai`, `google` | `ai.embedding` `_get_embeddings`, default/supported models |
| STT | `iap`, `openai`, `google` | `/ai/transcription`, `mail.call.artifact._transcribe_claimed_record` |
| Image | `iap`, `openai`, `google` | `ai.tool._generate_image_attachments` |

## UI

**Settings → AI** (`<app data-string="AI" name="ci_ai">`).

1. **Capability routing**: Chat / Embeddings / STT / Image  
2. **Providers**: enable Anthropic / OpenAI / Google; keys + per-capability model fields  

## Runtime rules

1. Capability=`iap` → stock `super()` / IAP routes.
2. Chat BYO → provider `complete()` in-request (Anthropic / OpenAI / Google).
3. Embeddings BYO → provider `embed()` with 1536-dim vectors.
4. STT=`openai` → Whisper multipart for batch; Realtime client secret for live browser STT. STT=`google` → Gemini multimodal batch only.
5. Image BYO → provider `generate()` → `inline_data` parts + attachments.
6. Missing enable/API key → `ValidationError` on save.
7. Do not monkeypatch `ai_utils.call_odoo_ai`.

## Acceptance criteria

1. Admin can route Chat / Embeddings / STT / Image independently to IAP, OpenAI, or Google (chat also Anthropic).
2. Credentials required before selecting a BYO provider on any capability.
3. BYO chat/embeddings/STT/image skip corresponding IAP routes (mocked tests).
4. Realtime STT with OpenAI mints an ephemeral session token (`ci_ai_realtime=true`).
5. Tests pass with mocks; docs under `.agent/docs`.

## Test plan (automated)

1. Config + ACL + settings round-trip for OpenAI / Google capability fields.
2. Chat adapters (Anthropic / OpenAI / Google) + session IAP skip.
3. Embeddings adapters + IAP skip.
4. STT batch mocks + OpenAI realtime client_secrets mock + credential validation.
5. Image generation mocks + `_generate_image_attachments` skips IAP path.
