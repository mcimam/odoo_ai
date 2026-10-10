# Feasibility: Bypass Odoo IAP and use your own LLM provider

> Companion to [odoo20-ai-architecture.md](./odoo20-ai-architecture.md).  
> Question: can a custom module make Enterprise `ai` talk to **our** models/providers instead of `https://ai.api.odoo.com`?

## Verdict

**Yes, technically feasible** — but there is **no official provider plugin**. Core `ai` hard-wires IAP. A custom module must either:

1. **Speak Odoo’s IAP protocol** (proxy behind `ai.endpoint`), or  
2. **Inherit and replace** the few transport methods (`_get_completions`, `_save_and_submit_request`, `_get_embeddings`, STT helpers).

Both keep Odoo’s agent/session/tool/RAG UI. Neither is a one-line config switch. Several IAP-only features (native web grounding, image gen, realtime STT tokens) need reimplementation or graceful disable.

Also factor **OEEL-1** (Enterprise license): extending `ai` for internal use under a valid Enterprise subscription is the usual case; redistributing a patched Enterprise AI stack is a different legal question — treat with counsel if you plan to ship it.

---

## Why IAP is sticky

| Layer | Coupling |
|-------|----------|
| Transport | `call_odoo_ai` / `call_odoo_ai_transport` in `ai/utils/ai_utils.py` → `{endpoint}/api/odoo_ai/{route}` + `account_token` / `dbuuid` |
| Async chat | `_save_and_submit_request` posts to `1/get_completions`, expects webhook `POST /ai/completion_result_ready` with **HMAC** (`odoo_ai-webhook` + `webhook_secret`) |
| Sync chat / tools | `_get_completions` → `1/get_completions_sync` |
| Embeddings | `ai.embedding._get_embeddings` → `1/get_embeddings`; vector size **fixed at 1536** |
| STT | Controllers / `mail_call_artifact` → `1/get_transcription`, realtime session token |
| Billing UX | `InsufficientCreditError` → IAP “no credit” notifications |
| Config | `ai.endpoint` only changes **host**, not protocol |

Message contract is typed in `ai/utils/types.py` (`Message`, `ToolCallPart`, `CompletionResponse`, …). Your provider adapter must emit that shape (or map into it).

There is **no** `provider` / `api_key` field on `ai.agent` for customer keys.

---

## Option A — Protocol-compatible proxy (config + external service)

**Idea:** set `ir.config_parameter` `ai.endpoint` = your gateway. Gateway implements Odoo’s routes and calls OpenAI / Anthropic / local vLLM / etc.

Must implement at least:

| Route | Role |
|-------|------|
| `1/get_completions` | Accept messages/tools/webhook_*; call LLM; **callback** Odoo webhook with HMAC |
| `1/get_completions_sync` | Same payload, return `{ result: AssistantMessage }` |
| `1/get_embeddings` | Return 1536-dim vectors (or change Odoo Vector size too) |
| Optional | transcription / realtime / embedding model list / scraper |

Webhook callback must match:

```text
POST /ai/completion_result_ready
body: request_uuid, llm_result | False, llm_error, signature
signature = hmac("odoo_ai-webhook", (request_uuid, llm_result, llm_error), secret=webhook_secret)
success payload: llm_result = { "result": <AssistantMessage> }
```

**Pros:** no (or minimal) Python inherit; survives more Odoo upgrades if protocol stays stable.  
**Cons:** you reverse-engineer / track Odoo’s private API; must handle async postcommit submit + retries; IAP token params still sent (ignore them).

---

## Option B — Custom Odoo module (inherit transport hooks) ← best fit for `modules/odoo_ai`

**Idea:** addon depending on `ai` that overrides:

| Model / method | Path |
|----------------|------|
| `ai.session._get_completions` | Sync completions (server actions, tools, one-shots) |
| `ai.session._save_and_submit_request` | Async Discuss chat → call your provider, then either call `_continue_agent_loop` yourself or emulate webhook |
| `ai.embedding._get_embeddings` | RAG vectors |
| Optional | `ai.embedding._get_default_embedding_model`, STT controller helpers, image/web tools |

For async chat, two sub-patterns:

1. **In-process:** after commit (or instead of IAP postcommit), call your LLM, then `session._continue_agent_loop({'kind': 'success', 'message': ...})` on a fresh cursor (same pattern as IAP rescue).  
2. **Keep webhook:** your worker POSTs to `/ai/completion_result_ready` with correct HMAC (reuse Odoo’s secret from session state).

Settings model: store provider, base URL, API key (System Parameters or a dedicated `ai.provider` model), default chat/embedding models.

**Pros:** full control; can disable IAP credit errors; natural place for multi-provider UI.  
**Cons:** must track Enterprise `ai` upgrades (session loop, tool schema, part types change); monkeypatching `call_odoo_ai` is **worse** than inherit because `ai_session` binds the function at import time — override methods instead.

Do **not** rely on patching `odoo.addons.ai.utils.ai_utils.call_odoo_ai` alone; `ai_session` imports it into its own namespace.

---

## Option C — Parallel stack (don’t reuse `ai`)

Rebuild agents/chat/tools yourself (Community-friendly). Huge cost; loses Discuss integration, composers, `ai_agentic`, MCP, domain `ai_*` modules. Only justified if you cannot use Enterprise `ai` at all.

---

## Feature coverage matrix

| Feature | Reuse with own provider? | Notes |
|---------|--------------------------|-------|
| Discuss agent chat + tool loop | Yes | Override async + sync completions |
| Skills / `ir.actions.server` tools | Yes | Tool schemas stay; LLM must return `tool_call` parts |
| Composers / prompt buttons | Yes | No IAP dependency |
| `ai_fields` / server actions | Yes | Uses sync `_get_completions` / agent one-shot |
| `ai_mcp` | Yes | Tools run in Odoo; LLM not involved in MCP path |
| RAG | Yes, with care | Embeddings must match **1536** dims unless you change `Vector(size=1536)` + reindex |
| Native `web_grounding` | Hard | IAP/provider-side; use web-search **skill/tool** instead |
| Native `image_generation` | Hard | Reimplement tool against DALL·E / Flux / etc. |
| Realtime / batch STT | Medium | Separate API; realtime token flow is IAP-specific |
| URL scraper IAP | Optional | Separate host; can skip or replace |
| IAP credits / `iap_paid_service` | Bypass | Never call Odoo AI → no Odoo AI credit burn |

---

## Recommended design for this workspace

For `modules/odoo_ai` (or similar):

1. Depend on Enterprise `ai` (+ optionally `ai_agentic`).  
2. Add `ai.provider.config` (or system params): `provider`, `base_url`, `api_key`, `chat_model`, `embedding_model`, `enabled`.  
3. Implement a thin **provider adapter** (OpenAI-compatible first — covers OpenAI, Azure, many local gateways).  
4. Inherit:
   - `ai.session` → `_get_completions` + `_save_and_submit_request` (when config enabled)
   - `ai.embedding` → `_get_embeddings` (+ default model helpers)  
5. Map provider responses → Odoo `AssistantMessage` / `tool_call` parts.  
6. Disable or stub: credit notifications, image gen, native web grounding until implemented.  
7. Keep embedding dim = **1536** initially (e.g. `text-embedding-3-small` truncated/dimensions API, or `text-embedding-ada-002`).

Fallback: if config disabled → call `super()` and keep stock IAP.

---

## Risks

1. **Upgrade churn** — `ai.session` (~1400 LOC) and message schemas evolve; pin/test against Enterprise 20.0.  
2. **Async reliability** — must match postcommit / multi-worker / webhook auth behavior.  
3. **Tool-calling quality** — not all models honor Odoo’s tool schema / `ask_user_question` patterns.  
4. **Security** — API keys in DB; public webhook only safe with HMAC; don’t expose keys to JS.  
5. **License / ToS** — Enterprise OEEL-1 + Odoo AI service terms; confirm your use case.  
6. **False simplicity of `ai.endpoint`** — pointing it at OpenAI’s URL **will not work**; path and payload are Odoo-specific.

---

## Bottom line

| Approach | Feasible? | Effort | Keeps Enterprise AI UX? |
|----------|-----------|--------|-------------------------|
| A. Compatible proxy | Yes | Medium (external service) | Yes |
| B. Inherit transport in custom module | Yes | Medium–high | Yes |
| C. New stack without `ai` | Yes | Very high | No |
| Config-only / official BYO key | **No** | — | — |

**Recommendation:** Option **B** (custom module overriding session + embedding transport), optionally plus a small OpenAI-compatible gateway. Treat IAP as fallback when your provider is disabled.
