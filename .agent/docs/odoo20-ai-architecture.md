# Odoo 20 AI — Architecture Analysis

> Generated for agent reuse. **Do not re-analyze whole trees** unless verifying a change against sources listed below.
>
> Analyzed: 2026-09-28 · Community: `odoo20` · Enterprise branch: `20.0`

## Verdict (read this first)

1. **Community Odoo 20 has no AI addons.** There is no `ai*` / LLM module under `odoo20/addons`.
2. **All AI is Enterprise** (`OEEL-1`), rooted in Hidden module `ai`, with ~50 `ai_*` satellites.
3. **LLM calls never use customer OpenAI/Anthropic keys.** Completions, embeddings, and STT go through **Odoo IAP** → default `https://ai.api.odoo.com` (`iap.account` service `odoo_ai`).
4. **Runtime mental model:** Composer → Agent → Discuss `ai_chat` + `ai.session` → IAP completion (async webhook or sync) → tool loop (`ir.actions.server` / `ai.tool`) → optional RAG (pgvector).
5. **Product UI / menus** live mainly in `ai_agentic`, not in core `ai`.

---

## Source paths

| Tree | Path |
|------|------|
| Community 20 | `/home/mcimam/Project/odoo/odoo/odoo20` |
| Enterprise 20 | `/home/mcimam/Project/odoo/odoo-enterprise` |
| Core AI | `…/odoo-enterprise/ai` |
| Agentic app | `…/odoo-enterprise/ai_agentic` |

Key files in core `ai`:

| Area | Path |
|------|------|
| Manifest | `ai/__manifest__.py` |
| Session / agent loop | `ai/models/ai_session.py` (~1400 LOC) |
| Agents / RAG | `ai/models/ai_agent.py` |
| Tools | `ai/models/ai_tool.py`, `ai/models/ir_actions_server.py` |
| Composers | `ai/models/ai_composer.py` |
| Embeddings | `ai/models/ai_embedding.py`, `ai/orm/field_vector.py` |
| IAP transport | `ai/utils/ai_utils.py` (`DEFAULT_ODOO_AI_ENDPOINT`, `call_odoo_ai_transport`) |
| HTTP | `ai/controllers/thread.py`, `ai/controllers/ai.py` |
| Instruction prompts | `ai/utils/agent_instructions_prompts.py` |

---

## Community vs Enterprise

| Concern | Community 20 | Enterprise 20 |
|---------|--------------|---------------|
| AI modules | **None** | `ai` + ~50 `ai_*` |
| LLM | N/A | IAP Odoo AI cloud |
| Depends | N/A | `mail`, `iap` (+ domain apps) |
| License | LGPL (core) | `OEEL-1` |
| Install gate | N/A | `ai_auto_install` installs `ai` only if **pgvector** is available |

`ai` declares `'iap_paid_service': True` and `pre_init_hook` `_pre_init_ai` (requires/creates PostgreSQL `vector` extension).

---

## Architectural spine (dependency graph)

```
mail ──► ai_auto_install ──(post_init if pgvector)──► ai ◄── iap
                                                          │
         ┌────────────────────────────────────────────────┤
         │                                                │
         ▼                                                ▼
      ai_mcp                                         ai_fields
   (export tools                                   (AI autofill fields)
    via /mcp)                                         │
                                                      ▼
                                              ai_server_actions
                                           (object_write ai_computed)

ai + attachment_indexation + base_automation
         │
         ▼
    ai_agentic  (application: menus, agent/skill CRUD, automations)
         ├─► ai_agentic_documents  (+ ai_documents_source)  UI bridge
         └─► ai_agentic_knowledge  (+ ai_knowledge)         UI bridge

Also auto-install onto host apps: ai_livechat, ai_documents*, ai_knowledge,
ai_html_builder, ai_website*, ai_crm*, ai_sale*, …
```

Full satellite catalog: [odoo20-ai-modules-catalog.md](./odoo20-ai-modules-catalog.md).

---

## Core concepts

### 1. Agent (`ai.agent`)

Configurable assistant: system prompt, skills, RAG sources, partner identity (avatar), optional sub-agents (`allowed_agent_ids`), embedding model, `is_system_agent`.

- Default system agent: XML id `ai.ai_default_agent` (“Odoo AI”).
- Instructions assembled in `_get_instructions()`: global protocol + agent protocol + usage context + RAG + skills sections (`utils/agent_instructions_prompts.py`).
- Launch chat: `action_launch_ai_chat(interface_key, res_model, res_id, …)`.
- One-shot text: `_generate_single_response()` → session `_get_direct_response()`.

### 2. Skill (`ai.skill`)

Bundle of instructions + optional tools (`ir.actions.server`).

- With tools → type **executable**; without → **guidance**.
- Native immutable skills include Generate Image, Web Search.
- Default agent always gets search/view/CRUD/image/web-search skills from data XML.
- Session always has tool `ai.ir_actions_server_load_skills` (lazy skill loading).

### 3. Tool (`ir.actions.server` + `ai.tool`)

Tools are **server actions** flagged for AI:

- `use_in_ai=True`, unique `ai_tool_name`, JSON `ai_tool_schema`
- Python code typically calls `record._ai_tool_*` methods on abstract model `ai.tool`
- MCP uses a **separate** flag `use_in_mcp` (`ai_mcp`) on the same tool metadata

Native tools (non-exhaustive): menus/views/search/CRUD/previews, load_skills, ask_user_question, start/continue_session (subagents), generate_image, web_search, compute_date, adjust_search, …

Security highlights:

- Model blocklist `AI_MODELS_BLOCKLIST` + most `ir.*`
- Create/update often require user confirmation unless `auto_confirm`
- Tools run with constrained sudo / access checks

### 4. Composer (`ai.composer`)

Maps a **UI surface** to an agent + default/quick prompts.

`INTERFACE_KEYS` (core):

| Key | Surface |
|-----|---------|
| `html_field_record` | Write in an HTML field |
| `mail_composer` | Write an email |
| `html_field_text_select` | Rewrite selection |
| `chatter_ai_button` | Help on a record |
| `html_prompt_shortcut` | Prompt → email |
| `systray_ai_button` | Systray Ask AI |
| `voice_transcription_component` | Voice summary buttons |
| `file_viewer_ai_button` | Ask AI on attachment |
| `media_dialog` | Image gen in media manager |

Lookup: `_get_composer_from_key_and_model(key, res_model)` (model-specific overrides default). Domain modules add more composers via data XML.

Prompt buttons: `ai.prompt.button` (QWeb-rendered, field injection).

### 5. Session (`ai.session` + `ai.session.event`)

Stateful agent loop bound to a Discuss channel (`channel_type=ai_chat`), agent, composer, optional `res_model`/`res_id`, parent session (subagents).

- History: `ai.session.event` JSON turns (user / assistant / tool results).
- Loop states: `ready` → `waiting_model` → (`waiting_confirmation` | `waiting_answer` | `waiting_client_result` | `waiting_external_result` | `waiting_child`) → … → `ready`.
- Limits: `ai.max_successive_calls` (default 30), `ai.max_tool_calls_per_call` (default 20).

### 6. RAG / embeddings

1. Sources (`ai.agent.source`) → attachments, scraped `ai.web.page`, or domain docs/articles.
2. Chunk text → `ai.embedding` rows with `Vector(1536)` (HNSW cosine).
3. Cron embeds via IAP `1/get_embeddings`.
4. Query-time: `_build_rag_context(prompt)` — embed query, similarity threshold (~0.9), top chunks.
5. Citations: LLM emits `[SOURCE:id]` / `[WEB_SOURCE:uuid]` → HTML superscripts (`utils/ai_citation.py`).
6. Requires **pgvector**.

Web search grounding: skill → tool → nested `_get_direct_response(..., web_grounding=True)` (tools + `web_grounding` together are forbidden; use the skill).

---

## End-to-end flows

### A. Interactive chat (primary)

```
UI posts in ai_chat channel
  → POST /ai/start_session_advance
  → mail.message._convert_to_parts()
  → ai.session._submit_agent_request(message)
       • append user event, RAG on first round
       • build instructions + tools
       • loop_state = waiting_model
  → postcommit: call_odoo_ai_transport('1/get_completions', webhook_*)
  → Odoo AI → POST /ai/completion_result_ready  (HMAC webhook)
  → _continue_agent_loop(result)
       • tool_calls → _advance_tool_batch() (may wait for user/client/child)
       • else → _format_final_message → channel.message_post
  → waits resumed via /ai/resume_pending_interaction
```

Entry methods to remember:

`action_launch_ai_chat` → `_submit_agent_request` → `_continue_agent_loop` / `_advance_tool_batch` → `_finish_exchange`.

### B. One-shot / server action

```
ai.agent._generate_single_response()
  or ir.actions.server._ai_action_run()
  → ai.session._get_direct_response()
  → sync IAP 1/get_completions_sync
```

Used by HTML prompt evaluation, transcription summary, `/ai/get_direct_response`, AI server actions, nested image/web tools.

### C. Launch from UI surfaces

```
aiChatLauncherService / form / systray patches
  → ai.agent.action_launch_ai_chat(interface_key, …)
  → resolve composer → agent → create ai_chat + ai.session
  → optional context (chatter, selection, attachment, image)
```

---

## IAP / cloud transport

| Item | Value |
|------|-------|
| Default endpoint | `https://ai.api.odoo.com` |
| Override | `ir.config_parameter` `ai.endpoint` |
| Auth | `iap.account` service `odoo_ai` + `database.uuid` |
| URL shape | `{endpoint}/api/odoo_ai/{route}` |
| Async chat | `1/get_completions` + webhook `/ai/completion_result_ready` |
| Sync | `1/get_completions_sync` |
| Embeddings | `1/get_embeddings` |
| STT | `1/get_transcription`, realtime session token routes |
| Scraper | separate IAP host (config `ai.scraper_base_url`, default iap-scraper) |

Helpers: `get_odoo_ai_connection_data()`, `call_odoo_ai_transport()` in `ai/utils/ai_utils.py`.

**No local model / BYO API key path in core `ai`.** Provider choice is server-side on Odoo AI; DB stores opaque `provider_metadata` on message parts.

Credit failures surface as `InsufficientCreditError` → IAP no-credit UX.

---

## HTTP routes (core)

| Route | Auth | Role |
|-------|------|------|
| `/ai/start_session_advance` | public (+ guest) | Start/continue agent turn |
| `/ai/completion_result_ready` | public (HMAC) | IAP LLM webhook |
| `/ai/resume_pending_interaction` | public (+ guest) | Confirmations / Q&A / client tools |
| `/ai/get_direct_response` | user | Sync completion |
| `/ai/transcription*` | user | Batch + realtime STT + summary |
| `/ai/url_scraper_result_ready/<uuid>` | public POST | Scraper callback |
| `/mail/rtc/recording/<id>/transcribe` | public JWT | Call recording STT |

Realtime UI uses Discuss/mail Store + bus (not a dedicated LLM websocket). Client one-way tools (`show_view`, `adjust_view`, `reload`, `do_action`) via bus `ai.session/client_tools` and `ai_client_tool_service.js`.

MCP (`ai_mcp`): `{odoo_url}/mcp` with Bearer API key scope MCP and/or OAuth 2.1 dynamic client registration.

---

## Frontend surfaces (core `ai` assets)

Loaded into `web.assets_backend` (plus public/livechat/portal subsets):

- Chat launcher / systray / form patches
- Discuss AI chat (composer, chat window, messaging menu, generating states)
- Client tool registry + user confirmation UI
- HTML editor AI (rewrite/draft, ChatGPT plugin, prompt plugin, media dialog)
- Mail composer AI drafting
- Voice transcription embedded component + audio worklets
- File viewer “Ask AI”
- Search/view NL adjustments / command palette hooks
- Prompt authoring widgets (field selectors, JSON schema)

`ai_agentic` adds agent panel (skills/sources/triggers), menus, command palette patches.

---

## Security / ACL summary

- Config models (`ai.agent`, `ai.skill`, `ai.composer`, …): users **read**, system **CRUD**
- `ai.session` / `ai.session.event` / embeddings / scraper batches: system CRUD only; users interact via controllers
- `discuss.channel.ai_agent_id` uses `groups=fields.NO_ACCESS` (write only via controlled flows)
- Webhook HMAC with `request_webhook_secret`
- Public/guest paths constrained; `_is_user_access_allowed()` default internal (overridden by livechat modules)

---

## Extension points (for custom / satellite modules)

| Hook | Where | Typical use |
|------|-------|-------------|
| New tools | `ir.actions.server` XML + `_ai_tool_*` on `ai.tool` | Domain actions |
| Skills | `ai.skill` data | Group tools + instructions |
| Agents | `ai.agent` data / inherit | Livechat bots, social, etc. |
| Composers / prompt buttons | `ai.composer`, `ai.prompt.button` | Text-draft per app |
| RAG sources | inherit `ai.agent.source` + `ai.embedding.mixin` | Documents, Knowledge |
| Session options | inherit `ai.session` (`_get_model_round_options`, …) | Website, marketing |
| Access | `_is_user_access_allowed` on `ai.agent` | Public/livechat |
| Composer agent pick | `_get_agent` on `ai.composer` | Per-record agents (helpdesk) |
| Client tools | `aiClientToolsRegistry` JS | Browser-side tool cmds |
| Automations | `base.automation` + AI agent (`ai_agentic`) or AI sort (`ai_documents`) | Scheduled / event AI |
| Fields | `ai_fields` (`_fill_ai_field`) | Autofill stored fields |
| MCP export | `use_in_mcp` on server actions | External MCP clients |
| HTML Builder | `ai_html_builder` JS patches | Website builder AI |

`base` helpers every model can override (`ai/models/models.py`): `_ai_read`, `_get_ai_context`, `_ai_serialize_fields_data`, `_ai_format_records`, `_ai_get_preview_metadata`, `_ai_field_names_to_truncate`.

---

## Architectural satellites (deep)

### `ai_auto_install`

Depends on `mail` only. Post-init: if pgvector available → install module `ai`.

### `ai_agentic`

Application shell: AI menus (Agents / Skills / Tools / Default Prompts), agent CRUD, Discuss agent panel, Self Update + Build Automation skills, `ai.automation.trigger`, ties `base.automation` to agents (runs in inspection channel with tools auto-confirmed).

### `ai_fields` / `ai_server_actions`

- Fields: `ir.model.fields` flags + prompt → cron/`_fill_ai_field` fills empty values.
- Server actions: `evaluation_type=ai_computed` on `object_write` reuses `_fill_ai_field`. Manifest notes possible future merge into `ai`.

### `ai_mcp`

Exposes tools with `use_in_mcp` at `/mcp` (`tools/list`, `tools/call`, …). Auth: API key scope MCP and/or OAuth 2.1. Independent of `ai_agentic`.

### `ai_livechat`

Channel rules can assign `ai_agent_id` as operator; visitor → AI session on livechat channel; optional forward to chatbot/human.

### Documents / Knowledge

| Module | Role |
|--------|------|
| `ai_documents` | Auto-sort docs (move/tag/rename tools + automation) |
| `ai_documents_source` | Docs as RAG sources (+ embedding mixin) |
| `ai_knowledge` | Article draft composers + articles as sources |
| `ai_agentic_documents` / `ai_agentic_knowledge` | JS bridges into agentic “Add Source” UI |

### `ai_html_builder` / `ai_website*`

Builder bus/data getters + media dialogs; `ai_website` is a large generator/scraper/tool stack; livechat preview cards via `ai.preview.card.mixin` (`ai_website_livechat` + bridges).

---

## Practical notes for this workspace

- Custom AI work should live under `modules/` (e.g. `modules/odoo_ai`) and **depend on / inherit** Enterprise `ai` patterns above — do not expect Community-only AI.
- Runtime needs: Enterprise addons path, IAP credits for `odoo_ai`, PostgreSQL **pgvector**.
- When debugging a flow: start at `action_launch_ai_chat` or `/ai/start_session_advance`, then `ai.session` loop state and IAP webhook.
- When adding a tool: ship `ir.actions.server` with schema + `_ai_tool_*`, optionally wrap in `ai.skill`, optionally set `use_in_mcp`.

---

## Related doc

- [Module catalog](./odoo20-ai-modules-catalog.md) — one-liners for every `ai_*` module.
