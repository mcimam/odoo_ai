# Agent docs

Persistent analysis for this workspace. Prefer these files over re-scanning full Odoo sources.

| Doc | When to read |
|-----|----------------|
| [odoo20-ai-architecture.md](./odoo20-ai-architecture.md) | How Odoo 20 AI works (community vs enterprise, runtime, tools, RAG, extension points) |
| [odoo20-ai-modules-catalog.md](./odoo20-ai-modules-catalog.md) | Inventory of all `ai` / `ai_*` enterprise modules and what each does |
| [odoo20-ai-bypass-iap-feasibility.md](./odoo20-ai-bypass-iap-feasibility.md) | Can we bypass Odoo IAP and use our own LLM provider? (options, hooks, risks) |
| [prd-ci-ai.md](./prd-ci-ai.md) | PRD for `ci_ai`: per-capability providers (IAP / Cursor / Anthropic), UI under Settings → AI |
| [roadmap-ci-ai-openai-google.md](./roadmap-ci-ai-openai-google.md) | v1.x roadmap: OpenAI + Google + OpenAI-compatible gateways (v1.11); next: OpenCode Zen (v1.12) |

## Custom module

- [`modules/odoo_ai/ci_ai`](../../modules/odoo_ai/ci_ai) — Path B provider router (IAP / Cursor / Anthropic / OpenAI full stack through v1.4)

## Source locations (outside this workspace)

- Community Odoo 20: `/home/mcimam/Project/odoo/odoo/odoo20` (`version_info = (20, 0, 0, …)`)
- Enterprise 20.0: `/home/mcimam/Project/odoo/odoo-enterprise` (git branch `20.0`)

This workspace (`/home/mcimam/Project/personal/odoo`) holds custom work under `modules/` and agent docs under `.agent/`. It does **not** vendor the Odoo core/enterprise trees.
