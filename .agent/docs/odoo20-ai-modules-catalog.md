# Odoo 20 Enterprise — AI module catalog

Companion to [odoo20-ai-architecture.md](./odoo20-ai-architecture.md).

Source: `/home/mcimam/Project/odoo/odoo-enterprise` (branch `20.0`).  
Community Odoo 20 has **zero** `ai*` addons.

License: almost all `OEEL-1`. Most satellites use `auto_install: True` when `ai` + host app are installed.

---

## Core / architectural

| Module | Depends | Purpose |
|--------|---------|---------|
| `ai` | `mail`, `iap` | **Runtime**: agents, sessions, tools, embeddings, Discuss UI, IAP LLM (Hidden) |
| `ai_auto_install` | `mail` | Installs `ai` if pgvector is available |
| `ai_agentic` | `ai`, `base_automation`, `attachment_indexation` | **Product app**: menus, agent/skill/composer CRUD, automation-as-agent |
| `ai_agentic_documents` | `ai_agentic`, `ai_documents_source` | JS: Add Source → Documents picker |
| `ai_agentic_knowledge` | `ai_agentic`, `ai_knowledge` | JS: Add Source → Knowledge articles |
| `ai_fields` | `ai` | AI autofill / computed fields + properties |
| `ai_server_actions` | `ai_fields` | `object_write` with `evaluation_type=ai_computed` |
| `ai_mcp` | `ai` | MCP server at `/mcp` (`use_in_mcp` tools, Bearer/OAuth) |
| `ai_livechat` | `ai`, `im_livechat` | AI agents as livechat operators via rules |
| `ai_html_builder` | `ai`, `html_builder` | HTML Builder ↔ AI bus / media dialogs |
| `ai_documents` | `ai`, `documents`, `base_automation` | Auto-sort documents (move/tag/rename) |
| `ai_documents_source` | `ai`, `documents` | Documents as agent RAG sources |
| `ai_knowledge` | `ai`, `knowledge` | Article composers + articles as RAG sources |

---

## Domain integrations

| Module | Depends (high level) | Purpose |
|--------|----------------------|---------|
| `ai_account` | `ai`, `account` | Accounting text-draft prompt buttons |
| `ai_account_reports` | `ai`, `account_reports` | Report analysis / audit tools on `ai.tool` / session |
| `ai_calendar` | `ai`, `calendar` | Calendar prompt buttons (data) |
| `ai_cloud_storage` | `ai`, `cloud_storage` | Cloud attachment handling for AI |
| `ai_crm` | `ai`, `crm` | Create leads via AI tools |
| `ai_crm_livechat` | `ai_crm`, `ai_livechat` | Leads from livechat AI agents |
| `ai_documents_account` | `ai_documents`, `documents_account` | Doc → accounting AI actions |
| `ai_documents_fleet` | `ai_documents`, `documents_fleet` | Doc → fleet AI actions |
| `ai_esg` | `ai`, `esg` | ESG context / emission factors for AI |
| `ai_helpdesk` | `ai`, `helpdesk` | Ticket embeddings + composers; per-team agents |
| `ai_hr_recruitment_integration_website_livechat` | `ai_website_livechat`, recruitment | Job preview cards in livechat |
| `ai_marketing_automation` | `ai`, `marketing_automation` | Generate MA campaigns with AI tools/session |
| `ai_marketing_automation_crm` | parent + CRM bridge | Extra skill/context for CRM rules |
| `ai_marketing_automation_loyalty` | parent + loyalty | Coupon rules context |
| `ai_marketing_automation_sms` | parent + SMS | SMS rules context |
| `ai_marketing_automation_website_sale` | parent + website_sale | eCommerce rules context |
| `ai_marketing_automation_whatsapp` | parent + WhatsApp | WhatsApp rules context |
| `ai_mass_mailing` | `ai`, `mass_mailing` | Mailing prompts + builder patch |
| `ai_product` | `ai`, `product` | Product composers |
| `ai_project` | `ai`, `project` | Project prompt buttons |
| `ai_purchase` | `ai`, `purchase` | Purchase prompt buttons |
| `ai_sale` | `ai`, `sale` | Sales prompt buttons |
| `ai_sale_margin` | `ai`, `sale_margin` | Margin-aware sale prompts |
| `ai_sale_stock` | `ai`, `sale_stock` | Sale+stock prompts |
| `ai_social` | `ai`, `ai_livechat`, `social` | Social post writing + livechat agents |
| `ai_stock` | `ai`, `stock` | Stock prompt buttons |
| `ai_timesheet_grid` | `ai`, `timesheet_grid` | Timesheet assistant composers |
| `ai_website` | `ai`, `website`, `ai_html_builder`, Unsplash | Large: site generation, scrape, website tools/session |
| `ai_website_livechat` | `ai_website`, `ai_livechat` | `ai.preview.card.mixin` for livechat cards |
| `ai_website_sale` | `ai_website`, `website_sale`, `ai_product` | eCommerce site AI |
| `ai_website_sale_slides` | `ai_website_sale`, slides | Courses on website-sale AI |
| `ai_website_appointment_sale` | `ai_website_sale`, appointment sale | Appointment types in website AI |
| `ai_website_appointment_livechat` | `ai_website_livechat`, appointment | Appointment preview cards |
| `ai_website_blog_livechat` | `ai_website_livechat`, blog | Blog preview cards |
| `ai_website_event_livechat` | `ai_website_livechat`, event | Event preview cards |
| `ai_website_sale_livechat` | `ai_website_livechat`, `ai_website_sale` | Product preview cards |
| `ai_website_slides_livechat` | `ai_website_livechat`, slides | Slides preview cards |
| `ai_website_helpdesk` | `ai_website_livechat`, helpdesk forum | Helpdesk portal AI UX (controllers/templates) |

---

## Counts

- Core package: `ai`
- Satellites listed: **50** (`ai_*`)
- Total AI-related enterprise modules: **51**

---

## Extension pattern cheat-sheet

Most domain modules only:

1. Add `ai.composer` / `ai.prompt.button` data for text drafting, **or**
2. Add `ir.actions.server` AI tools + optional `ai.skill`, **or**
3. Inherit `ai.session` / `ai.agent` for domain context, **or**
4. Implement `ai.preview.card.mixin` for livechat rich cards.

Heavier stacks: `ai_website`, `ai_documents`, `ai_marketing_automation`, `ai_helpdesk`, `ai_account_reports`.
