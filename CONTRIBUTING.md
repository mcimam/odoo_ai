# Contributing (Odoo guidelines)

This addons repo follows Odoo 20.0 contribution standards:

- [Coding guidelines](https://www.odoo.com/documentation/20.0/contributing/development/coding_guidelines.html)
- [Git guidelines](https://www.odoo.com/documentation/20.0/contributing/development/git_guidelines.html)

Cursor rules live in [`.cursor/rules/`](.cursor/rules/) and mirror those docs for agent-assisted work.

## Commit messages

Use the Odoo header form:

```text
[TAG] module: short imperative header

Why this change matters.
```

Example:

```text
[IMP] ci_ai: support OpenAI-compatible gateway presets

Allow cheaper BYO chat backends via allowlisted OpenAI-compatible hosts.
```

A template file is at [`.gitmessage`](.gitmessage). To use it in **this** repo only:

```bash
git config commit.template .gitmessage
```

(Do not set global git identity from this doc unless you intend to.)

## Module work

- Prefer one technical module per commit.
- Keep stable-branch diffs minimal; do not mass-reformat unrelated code.
- New community modules should use a vendor prefix (e.g. `ci_`).
