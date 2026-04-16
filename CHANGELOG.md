# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Fixed — e2e bootstrap test (`server/scripts/e2e_agent_bootstrap_install_use_uninstall.py`)

**Bug 1 — Hardcoded `codex.exe` failed on npm-installed Codex**

The test used `["codex.exe", ...]` in subprocess calls.  On machines where Codex
is installed via npm the binary is `codex.cmd`, not `codex.exe`.  Replaced with a
module-level `_resolve_exe()` helper that probes `.exe` → `.cmd` → bare name and
stores the result in `CODEX_EXE` / `CLAUDE_EXE` constants used throughout the file.
This also future-proofs the `claude` invocations (currently always `claude.exe` on
Windows, but the same probe pattern applies).

**Bug 2 — `CODEX_HOME` not set → test isolation broken**

Codex does not use `HOME` / `USERPROFILE` to locate its skill and rule directories;
it uses the `CODEX_HOME` environment variable instead.  Without this, all
`codex debug prompt-input` and `codex execpolicy check` calls read from the real
user's `~/.codex`, not the temporary home created for the test.  Effects:

- `_assert_codex_sees_ma3(env, True)` passed even before install (real home already
  has ma3), making it a no-op.
- `_assert_codex_sees_ma3(env, False)` after uninstall would always fail if the real
  home still had ma3.

Fix: `_fresh_env()` now sets `CODEX_HOME = str(home / ".codex")`.  The install
scripts write the skill junction and rule file to `$HOME\.codex\…`, which matches
`CODEX_HOME` exactly, so discovery works correctly after install and stops working
after uninstall.

**Bug 3 — Skill visibility pattern didn't match Codex ≥ 0.120 output**

`codex debug prompt-input` with a fresh `CODEX_HOME` (Codex 0.120+) formats user
skills as `- ma3: <description>`.  The test expected `- ma3:ma3:` (the legacy format
where both the junction directory name and the SKILL.md `name` field are shown).
Updated the check to accept both:

```python
visible = "- ma3:ma3" in proc.stdout or "- ma3: " in proc.stdout
```

---

## Earlier changes

See `git log` for full history.  Key milestones:

- `c6e33da` Add agent bootstrap and whitelist e2e coverage
- `1930126` fix: update agents.md install section from git clone to install.sh
- `2b6bffd` fix: symlink ma3 skill into ~/.codex/skills/ during install
- `0b321cf` Add warmup verification command
- `f88f64c` feat(client): add Claude Code plugin manifest and one-line installers
- `ad69376` Initial commit: 马妈妈 (ma3) — merge of server + client
