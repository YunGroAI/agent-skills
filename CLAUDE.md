# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Distributable Agent Skills for the **YunGroAI growth engine MCP**, published at https://github.com/YunGroAI/agent-skills and also packaged as a WorkBuddy connector (MCP + Skill). There is no application build, linter, test suite, or CI. "Development" means editing Markdown skill content, a few standalone Python helper scripts, and connector metadata.

**[AGENTS.md](AGENTS.md) is the authoritative authoring spec** (naming, frontmatter, MCP dependency declaration, client/machine-agnostic rules, forbidden terms, connector packaging fields, manual review checklist). Read it before changing anything under `skills/` or the root metadata.

## Commands

Install a skill (Vercel Labs `skills` CLI; needs Node.js/`npx`):

```bash
npx skills add YunGroAI/agent-skills --skill weixin-official-account-operator   # from public GitHub repo
npx skills add /absolute/path/to/agent-skills --skill weixin-official-account-operator   # from local checkout
```

Add `--list` to list available skills, `-g` for global install. Installing a skill never configures the MCP connection.

Local scripts in `skills/weixin-official-account-operator/scripts/` (pure local, no side effects beyond the output path):

```bash
python3 scripts/build_article.py article.md -o out.html [--theme tech | --primary #RRGGBB]  # lint → theme suggest → render; exits 1 if lint has ERRORs
python3 scripts/lint_article.py article.md
python3 scripts/render_theme.py --list            # or --suggest / --showcase out.html / --print-tokens
python3 scripts/prepare_image.py imgs/ -o wx_images   # requires Pillow
```

## Architecture

- **Root connector packaging** — `mcp.json` (single `YunGroAI` streamableHttp server → `https://agent.uboosts.com/mcp`), `connector-meta.json` (WorkBuddy market listing; bump `version` on any metadata change), `icon.svg`. Skills never read these at runtime.
- **Skills are standalone** — each `skills/<name>/SKILL.md` embeds the full `mcpServers` JSON inline and discovers the dependency by server name `YunGroAI`. The same JSON block is duplicated in `mcp.json`, `README.md`, and every `SKILL.md`; when the connection changes, update all copies together.
- **Skill layout** — `SKILL.md` is a router (task-type → which reference to read, prerequisites, hard constraints); long procedures live in `references/*.md`; `assets/themes.json` holds the 8 layout themes consumed by `render_theme.py`; `build_article.py` shells out to `lint_article.py` and `render_theme.py` via `sys.executable`.
- **Core behavioral constraints of the WeChat skill** (keep intact when editing): multi-account calls must carry a user-named `connection_id`; side effects (image upload, drafts, publish, preview, messages, menus) are batched behind explicit user confirmation — iterate locally, write to WeChat once.

## Gotchas

- Everything under `skills/` must stay client- and machine-agnostic: no `~/.workbuddy/...` paths, WorkBuddy-specific UI/tools, loopback URLs, or absolute local paths. `minWorkbuddyVersion` belongs only in `connector-meta.json`.
- `.workbuddy/`, `outputs/`, and `.wbapp_*.genie` are local client artifacts (gitignored). Client-generated files like `_user_meta.json` or extra frontmatter keys (e.g. `agent_created`) must not be committed into a skill.
- README and skill content are written in Chinese; keep that language when editing them.
