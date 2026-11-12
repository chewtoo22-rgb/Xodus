# Xodus for Codex CLI

Repository conventions live in `.agents/skills/Xodus/SKILL.md` (Claude Code reads the identical copy at `.claude/skills/Xodus/SKILL.md`). Keep the two files identical.

No repo-local MCP servers or Codex config are committed: this repository pins its inputs, and unpinned `npx …@latest` servers would run unreviewed code in every session. Keep personal MCP servers and credentials in `~/.codex/config.toml`.
