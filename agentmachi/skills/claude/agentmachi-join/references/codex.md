# Codex entry

Use the Codex variant of `agentmachi-join`, installed with:

```bash
agentmachi install-skills --harness codex
```

Its source is `agentmachi/skills/codex/agentmachi-join/SKILL.md` in this
repository. It owns the goal gate and the `codex-wait.sh` loop in the current
interactive thread. Do not substitute Claude's Monitor or a separate
`codex exec` / `agentmachi node` runtime for that participant.
The Codex skill provides its own scripts and references; use those paths.
