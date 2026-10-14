# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is the **single source of the skill development standard** for this repo (AGENTS.md only points here). To create or modify a skill, follow the project skill [`.claude/skills/skill-development`](.claude/skills/skill-development/SKILL.md); mechanically checkable rules are enforced by CI ([`.github/workflows/skills-standard.yml`](.github/workflows/skills-standard.yml)).

## What this repo is

Distributable Agent Skills for the **YunGroAI growth engine MCP**, published at https://github.com/YunGroAI/agent-skills and also packaged as a WorkBuddy connector (MCP + Skill). There is no application build. "Development" means editing Markdown skill content, a few standalone Python helper scripts, and connector metadata. README and skill content are written in Chinese; keep that language when editing them.

## Commands

Install skills (Vercel Labs `skills` CLI; needs Node.js/`npx`). Add `--list` to list skills, `-g` for a global install. Installing a skill never configures the MCP connection.

```bash
npx skills add YunGroAI/agent-skills --skill '*'                                       # all skills from GitHub; rerun to update and pick up new skills
npx skills add YunGroAI/agent-skills --skill yungroai-skills weixin-official-account-operator
npx skills add /absolute/path/to/agent-skills --skill '*'                              # local checkout
```

Skill-local scripts (run from the skill directory; pure local, no side effects beyond the output path):

```bash
python3 scripts/build_article.py article.md -o out.html [--theme tech | --primary #RRGGBB]  # weixin: lint → theme → render
python3 scripts/lint_article.py article.md
python3 scripts/score_title.py "标题一" "标题二"            # heuristic title scores
python3 scripts/render_theme.py --list                 # or --suggest / --showcase out.html / --print-tokens
python3 scripts/render_theme.py article.md --cards     # theme-picker card options (top 3 + fallback, JSON)
python3 scripts/render_theme.py article.md --compare cmp.html [--themes a,b,c]   # the user's article in several themes
# build_article.py / render_theme.py also take --density large|standard|compact
python3 scripts/check_html.py out.html [--final] [--preview prev.html]   # WeChat HTML compliance; --final requires mmbiz image URLs
python3 scripts/prepare_image.py imgs/ -o wx_images [--cover]  # requires Pillow; --cover emits 2.35:1 + 1:1 crops
```

There are no unit tests. Smoke-test the weixin scripts with `python3 scripts/build_article.py assets/sample-article.md -o /tmp/s.html`.

Run the CI checks locally with [`act`](https://github.com/nektos/act): `act pull_request -W .github/workflows/skills-standard.yml`. Without `act`, the checks are inline Python heredocs in that workflow (needs `pyyaml`, `pyflakes`); extract a step's script and run it from the repo root — the version-bump step reads `BASE` (set `BASE=$(git rev-parse HEAD)` to compare the working tree against the last commit).

## Architecture

- **Root connector packaging** — `mcp.json` (single `YunGroAI` streamableHttp server), `connector-meta.json` (WorkBuddy market listing), `icon.svg`. Skills never read these at runtime.
- **Skills are installed per directory** — `npx skills add` installs only `skills/<name>/`, so a skill must not reference repo files outside its directory. Business skills depend on the sibling skill `yungroai-skills` by name only.
- **Skill layout** — `SKILL.md` is a router (task type → which reference to read, prerequisites, hard constraints); long procedures live in `references/*.md`; `assets/` and `scripts/` hold skill-specific data and tools.
- **Entry skill `yungroai-skills`** — the only place that defines the MCP dependency (full `mcpServers` config, check and guided install in the current agent) the 「技能目录」 table (business skill → when to use it), and skill install/update ([`references/skill-sync.md`](skills/yungroai-skills/references/skill-sync.md)). Users install only the manager. At task start it checks MCP, runs `npx skills update` at most once per 24h (timestamp in `${XDG_CACHE_HOME:-~/.cache}/yungroai-skills/last-check`; opt out with `YUNGROAI_SKILLS_AUTO_UPDATE=0`; skipped when the manager was not installed from `YunGroAI/agent-skills`), matches the user's task against the catalog, installs only the missing matched skill with `npx skills add YunGroAI/agent-skills --skill <name>`, then reads that skill's `SKILL.md` and continues. Every business skill starts with the standard 「前置检查」 section, which hands off to the manager (and guides installing it if missing). There is no sync script: everything goes through the skills CLI (git clone, so no GitHub API rate limit). The console's "connect AI assistant" prompt installs only `yungroai-skills` plus the MCP connection.
- **Templates** — `.claude/skills/skill-development/assets/preflight-section.md` is the canonical 「前置检查」 section; `.claude/skills/skill-development/assets/interaction-section.md` is the canonical 「交互规范」 section. That project skill is `metadata.internal: true`, so the CLI never lists or installs it.
- **weixin scripts** — `build_article.py` is a thin pipeline that shells out to `lint_article.py` → `render_theme.py` → `check_html.py --strict` (stops on ERRORs); `:::html` fenced blocks pass Agent-written components through the renderer verbatim and are skipped by the linter, so `check_html.py` is their only gate; `assets/themes.json` is the single source of theme tokens for `render_theme.py`, and `assets/theme-showcase.html` is generated by `render_theme.py --showcase`.
- **MCP tool names and params** — the skill's tool references must match the live YunGroAI server (sibling repo `weixin-mcp`, `docs/tool-contracts.json`); account selection is the `account_id` param. Newer server tools are written as "use if listed, else the old flow" so the skill works against both server versions.
- **WeChat skill constraints** (keep intact): each session binds one account (account card, first account preselected, "add account" via WeChat third-party-platform QR authorization) and every call carries its `account_id`; side effects (uploads, drafts, publish, preview, messages, tags, deletions) are batched behind explicit user confirmation.

## Skill development standard

### Structure and naming (CI)
- Directory name = frontmatter `name`: lowercase kebab-case, ≤ 64 chars, unique.
- Frontmatter has `name`, nonempty `description`, and `metadata.version` (semver). No client-generated keys (e.g. `agent_created`) or files (e.g. `_user_meta.json`).
- **Bump `metadata.version` for any change under `skills/<name>/`** — users only receive updates when the version increases. Patch = wording/fixes, minor = new capability, major = breaking workflow change.
- Business skills contain the template 「前置检查」 section verbatim before the startup steps, and must not contain `mcpServers` config or update scripts — those live only in `yungroai-skills` (CI).
- Every skill (manager included) contains the template 「交互规范」 section verbatim (CI); business skills put it right after 「前置检查」.
- **Catalog sync**: adding, removing, or renaming a business skill, or changing its scope/triggers (`description`, capability boundaries), requires updating its row in the 「技能目录」 table of `skills/yungroai-skills/SKILL.md` and a patch bump of the manager — otherwise the manager cannot match or install it. Internal-only changes need no catalog edit. CI checks the table matches the business skills one-to-one and that a changed `description` comes with a manager change.
- Every relative Markdown link resolves; no TODO placeholders in `SKILL.md`.

### Content
- Keep `SKILL.md` to routing, prerequisites, and essential constraints; put longer procedures in descriptively named `references/*.md`.
- Use clear headings and fenced, valid JSON for config examples. Python: stdlib-first, four-space indent, small direct checks, must pass pyflakes (CI).

### Interaction: intent first, option cards (manual review)
Every point where a skill needs user input, a choice, or a confirmation follows the 「交互规范」 section:
- **Analyze intent first**: infer from the user's words, context, and data already read; don't ask what can be inferred or defaulted, only what changes the result, and turn inferences into the recommended default.
- **Option cards, not open questions**: 2–4 concrete options per question, recommended option first and marked 「（推荐）」 with a one-line reason, always an 「其他 / 我来补充」 escape for free input or edits. Use the agent's question/option-card tool when it has one, otherwise a numbered list answerable with a number.
- **One round**: group the questions for a step (≤ 4 per group); echo briefs, plans and confirmations as short structured cards with 「确认 / 调整某一项 / 换个方向」.
- **User language**: no internal parameter names or error codes in options.
- **Cards never replace approval**: side-effect actions need the user to actively pick an explicit 「确认执行」 option naming the action, target and impact; irreversible actions are never the recommended default.
- Write the concrete cards for a skill's own pause points into its references (e.g. `references/interaction-cards.md`), described by intent rather than tied to any client UI.

### MCP dependency
- Only `yungroai-skills/SKILL.md` declares the dependency: server name `YunGroAI` plus the full `mcpServers` config identical to `mcp.json` (CI). Update `mcp.json`, `README.md`, and the manager together, and bump the manager's version.
- Discover the connection by name only, including user-configured local services; no runtime URL/HTTPS/certificate checks, and never replace an existing connection. Name matching selects a service; it does not prove identity.
- The manager checks for `YunGroAI` at task start and, if missing, **proactively guides installation in the current agent**: show the config, identify the agent, add the connection itself with user consent when the agent can (otherwise give that agent's official steps), reload/authorize, then re-check before any `YunGroAI` tool is called. A missing connection is never reported as an account permission problem.

### Client- and machine-agnostic (CI)
Nothing under `skills/` (nor README/connector config) may contain client-specific paths, tools, or UI (`~/.workbuddy`, `present_files`, `workbuddy_sites_deploy`, `minWorkbuddyVersion`, connector management pages), loopback/local-dev URLs, machine-specific absolute paths, credentials or fixed tokens, or internal/obsolete terms (`litellm`, `agent-platform`, `weixin-mcp`, `aigw.uboosts.com`, `x-user-context`, `debug=true`, `env=dev`).

### Connector packaging (CI)
- `mcp.json`: exactly one server `YunGroAI`, `type: streamableHttp`, `url: https://agent.uboosts.com/mcp`, no credentials.
- `connector-meta.json`: nonempty `name`, `name_zh`, `name_en`, `description`, `description_zh`, `description_en`, `source` (`yungroai`), `version` (semver), `minWorkbuddyVersion`, `examples_zh`, `examples_en` (2–5 each); `type: mcp`. Bump `version` whenever packaged content changes.
- Keep a valid root `icon.svg`, the manager skill, and at least one business skill.

### Manual review before submitting (not automatable)
- A business skill installed without the manager still guides the user to install the manager; everything works on any MCP client.
- Authorization, publishing, and side-effect instructions describe actual behavior; report which checks you actually performed.
- Every place the skill asks the user something follows 「交互规范」: intent inferred first, option cards with a recommended default, no bare open-ended questions.

### Commits and PRs
Conventional, imperative subjects naming the skill or doc changed. PRs describe user-facing behavior, list affected skills with their new versions, and report validation results.

## Local artifacts

`.workbuddy/`, `outputs/`, and `.wbapp_*.genie` are local client artifacts (gitignored); never commit them.
