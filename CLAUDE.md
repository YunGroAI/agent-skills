# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is the **single source of the skill development standard** for this repo (AGENTS.md only points here). To create or modify a skill, follow the project skill [`.claude/skills/skill-development`](.claude/skills/skill-development/SKILL.md); mechanically checkable rules are enforced by CI ([`.github/workflows/skills-standard.yml`](.github/workflows/skills-standard.yml)).

## What this repo is

Distributable Agent Skills for the **YunGroAI growth engine MCP**, published at https://github.com/YunGroAI/agent-skills and also packaged as a WorkBuddy connector (MCP + Skill). There is no application build. "Development" means editing Markdown skill content, a few standalone Python helper scripts, and connector metadata. README and skill content are written in Chinese; keep that language when editing them.

## Commands

Install a skill (Vercel Labs `skills` CLI; needs Node.js/`npx`). Add `--list` to list skills, `-g` for a global install. Installing a skill never configures the MCP connection.

```bash
npx skills add YunGroAI/agent-skills --skill weixin-official-account-operator         # public GitHub repo (auto-updatable)
npx skills add /absolute/path/to/agent-skills --skill weixin-official-account-operator # local checkout (no auto-update)
```

Skill-local scripts (run from the skill directory; pure local, no side effects beyond the output path):

```bash
python3 scripts/check_update.py --check-only --force   # every skill: version check (see Auto-update)
python3 scripts/build_article.py article.md -o out.html [--theme tech | --primary #RRGGBB]  # weixin: lint → theme → render
python3 scripts/lint_article.py article.md
python3 scripts/render_theme.py --list                 # or --suggest / --showcase out.html / --print-tokens
python3 scripts/prepare_image.py imgs/ -o wx_images    # requires Pillow
```

Run the CI checks locally with [`act`](https://github.com/nektos/act): `act pull_request -W .github/workflows/skills-standard.yml`.

## Architecture

- **Root connector packaging** — `mcp.json` (single `YunGroAI` streamableHttp server), `connector-meta.json` (WorkBuddy market listing), `icon.svg`. Skills never read these at runtime.
- **Skills are standalone** — `npx skills add` installs only `skills/<name>/`, so a skill must not reference any other repo file. Each `SKILL.md` embeds the full `mcpServers` JSON and discovers the dependency by server name `YunGroAI`; the same block lives in `mcp.json`, `README.md`, and every `SKILL.md`.
- **Skill layout** — `SKILL.md` is a router (task type → which reference to read, prerequisites, hard constraints); long procedures live in `references/*.md`; `assets/` and `scripts/` hold skill-specific data and tools.
- **Auto-update** — every skill carries `metadata.version` and an identical `scripts/check_update.py`. At task start the skill runs it: it compares the local version with `main` on GitHub and, for installs from `YunGroAI/agent-skills` (found in `skills-lock.json` or the global `.skill-lock.json`), runs `npx skills update <name> -p|-g -y`. Local-path and marketplace installs only get a hint. Network failures are silent; 24 h throttle; `YUNGROAI_SKILLS_AUTO_UPDATE=0` disables auto-apply.
- **Templates** — `.claude/skills/skill-development/assets/` holds the canonical `check_update.py`, MCP-dependency section, and auto-update section. That project skill is `metadata.internal: true`, so the CLI never lists or installs it.
- **WeChat skill constraints** (keep intact): multi-account calls carry a user-named `connection_id`; side effects (uploads, drafts, publish, preview, messages, menus) are batched behind explicit user confirmation.

## Skill development standard

### Structure and naming (CI)
- Directory name = frontmatter `name`: lowercase kebab-case, ≤ 64 chars, unique.
- Frontmatter has `name`, nonempty `description`, and `metadata.version` (semver). No client-generated keys (e.g. `agent_created`) or files (e.g. `_user_meta.json`).
- **Bump `metadata.version` for any change under `skills/<name>/`** — users only receive updates when the version increases. Patch = wording/fixes, minor = new capability, major = breaking workflow change.
- `scripts/check_update.py` is a byte-identical copy of the template; `SKILL.md` contains the template MCP-dependency section and auto-update section verbatim, in that order, before the startup steps.
- Every relative Markdown link resolves; no TODO placeholders in `SKILL.md`.

### Content
- Keep `SKILL.md` to routing, prerequisites, and essential constraints; put longer procedures in descriptively named `references/*.md`.
- Use clear headings and fenced, valid JSON for config examples. Python: stdlib-first, four-space indent, small direct checks, must pass pyflakes (CI).

### MCP dependency
- Each skill declares its dependency inline: server name `YunGroAI` plus the full `mcpServers` config identical to `mcp.json` (CI). Update `mcp.json`, `README.md`, the MCP-dependency template, and every `SKILL.md` together.
- Discover the connection by name only, including user-configured local services; no runtime URL/HTTPS/certificate checks, and never replace an existing connection. Name matching selects a service; it does not prove identity.
- Every skill embeds the standard section `assets/mcp-dependency-section.md` verbatim (CI). It makes the agent check for `YunGroAI` at task start and, if missing, **proactively guide installation in the current agent**: show the config, identify the agent, add the connection itself with user consent when the agent can (otherwise give that agent's official steps), reload/authorize, then re-check before calling any tool. A missing connection is never reported as an account permission problem.

### Client- and machine-agnostic (CI)
Nothing under `skills/` (nor README/connector config) may contain client-specific paths, tools, or UI (`~/.workbuddy`, `present_files`, `workbuddy_sites_deploy`, `minWorkbuddyVersion`, connector management pages), loopback/local-dev URLs, machine-specific absolute paths, credentials or fixed tokens, or internal/obsolete terms (`litellm`, `agent-platform`, `weixin-mcp`, `aigw.uboosts.com`, `x-user-context`, `debug=true`, `env=dev`).

### Connector packaging (CI)
- `mcp.json`: exactly one server `YunGroAI`, `type: streamableHttp`, `url: https://agent.uboosts.com/mcp`, no credentials.
- `connector-meta.json`: nonempty `name`, `name_zh`, `name_en`, `description`, `description_zh`, `description_en`, `source` (`yungroai`), `version` (semver), `minWorkbuddyVersion`, `examples_zh`, `examples_en` (2–5 each); `type: mcp`. Bump `version` whenever packaged content changes.
- Keep a valid root `icon.svg` and at least one skill.

### Manual review before submitting (not automatable)
- A skill installed alone has complete dependency setup instructions and works on any MCP client.
- Authorization, publishing, and side-effect instructions describe actual behavior; report which checks you actually performed.

### Commits and PRs
Conventional, imperative subjects naming the skill or doc changed. PRs describe user-facing behavior, list affected skills with their new versions, and report validation results.

## Local artifacts

`.workbuddy/`, `outputs/`, and `.wbapp_*.genie` are local client artifacts (gitignored); never commit them.
