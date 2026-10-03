# Repository Guidelines

## Project Structure & Module Organization

This repository contains reusable Agent Skills for the YunGroAI growth engine MCP, packaged as a WorkBuddy connector (MCP + Skill). Connector metadata lives at the repository root: `connector-meta.json` (market listing, `source: yungroai`), `mcp.json` (single streamableHttp server config matching the documented YunGroAI endpoint), and `icon.svg`. Each skill lives in `skills/<skill-name>/` and has a required `SKILL.md` with YAML frontmatter. Put task-specific detail in `references/*.md` and link it from the skill entrypoint; the current example is `skills/weixin-official-account-operator/`. `README.md` documents installation through the skills CLI. This file defines the project's skill authoring rules. There is no application build, asset pipeline, automated repository validator, or CI validation workflow.

## Build, Test, and Development Commands

- `npx skills add YunGroAI/agent-skills --skill weixin-official-account-operator` installs the skill from the public GitHub repository (https://github.com/YunGroAI/agent-skills) into the current project.
- `npx skills add /absolute/path/to/agent-skills --skill weixin-official-account-operator` installs the skill from a local checkout. For either source, add `--list` to list skills or `-g` for a global install. Installing a skill does not configure the MCP connection.

## Coding Style & Naming Conventions

Use unique lowercase kebab-case names for skill directories and frontmatter `name` values; they must match and be at most 64 characters. Start every `SKILL.md` with YAML frontmatter containing `name` and a nonempty `description`. Do not leave TODO placeholders in the skill entrypoint. Keep `SKILL.md` focused on routing, prerequisites, and essential constraints. Place longer procedures in descriptive reference files such as `references/publishing.md`, and ensure every linked reference exists relative to the skill directory. Use clear Markdown headings and fenced, valid JSON for configuration examples. Match the existing Python style: four-space indentation and small, direct checks. No formatter or linter is configured.

## Testing Guidelines

Before submitting changes, manually review the affected files against these authoring rules:

- Check skill names, frontmatter, descriptions, reference links, and absence of unfinished placeholders.
- Compare the complete MCP examples in every skill and `README.md` with `mcp.json`; update all copies together when the connection changes.
- Confirm a skill installed alone has all dependency setup instructions and does not need repository files or a particular client or machine.
- Check connector metadata and the SVG icon against the requirements below when packaging changes.
- Review authorization and publishing instructions for accurate behavior, and report the checks actually performed.

## Commit & Pull Request Guidelines

The repository has no commits yet, so it has no established commit-message convention. Use a concise, imperative subject that identifies the skill or documentation changed. In pull requests, describe the user-facing behavior, list affected skills, report validation results, and link an issue when one exists. Include screenshots only for changes with a visual result.

## Security & Configuration

Skills are distributed standalone: each one explicitly declares its MCP dependency inline (server name `YunGroAI` plus the full connection config) and never reads repository files at runtime. The root `mcp.json` is only the packaging copy used by the connector. Every skill and `README.md` must carry the same complete `mcpServers` JSON example, and skills must not refer to repository paths for dependency setup. When a skill cannot find the connection, it must treat that as a missing dependency and walk the user through setup with the embedded config, following that client's own MCP configuration method, before invoking any tool.

Discover the MCP dependency by the configured server name `YunGroAI`, including user-configured local development services. Do not require runtime URL, HTTPS, or certificate checks in the skill, or replace an existing local connection with the default remote config. Name matching selects the user-configured service; it does not prove service identity. Missing connections require installation guidance using the embedded default config and a fresh availability check afterward.

Keep every file under `skills/` client-agnostic and machine-agnostic: no client-specific config paths or UI (for example `~/.workbuddy/*.json`, a connector management page, `workbuddy_sites_deploy`, or `minWorkbuddyVersion`), no hardcoded local-development URLs or loopback addresses in distributed examples (user-configured local connections are supported), and no hardcoded machine-specific absolute paths. Do not add credentials, fixed tokens, or service implementation details to skills, README, or connector configuration. Do not include internal or obsolete terms and settings such as `litellm`, `agent-platform`, `weixin-mcp`, `https://aigw.uboosts.com/uboosts/mcp`, `x-user-context`, `debug=true`, or `env=dev` in those files.

## Connector Packaging Requirements

- `mcp.json` configures exactly one server named `YunGroAI`, using `streamableHttp` and the HTTPS endpoint `https://agent.uboosts.com/mcp`. Never embed credentials in headers or environment values; use placeholders if configuration requires them.
- `connector-meta.json` must contain nonempty `name`, `name_zh`, `name_en`, `description`, `description_zh`, `description_en`, `source`, `version`, `minWorkbuddyVersion`, `examples_zh`, and `examples_en` fields. Keep `type` as `mcp`, `source` as lowercase kebab-case (`yungroai`), and `version` in numeric `major.minor.patch` format. Each language's examples list contains 2–5 examples. Increment the version when updating metadata.
- Keep a valid `icon.svg` at the repository root and at least one skill in `skills/`.
