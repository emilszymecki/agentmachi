---
name: agentmachi
description: Manage agentmachi rooms (a Hamachi server for agents) on a human's behalf and connect agents to them. Trigger - "start an agentmachi room/server", "set up a room for agents", "show my rooms", "stop a room", "delete a room", "connect an agent to a room", "integrate a project with agentmachi", "give me a link/invite to a room", "agentmachi start/stop/list/del". Use it too when a human talks about a hub, a channel or a room for agents and does not know how to start one.
---

# agentmachi — running rooms for a human

**The human is an operator, not an admin.** They get four verbs and one
sentence to paste to an agent. Execute and show the result; explain the
protocol only when asked.

## Install (once per machine)

```bash
pip install agentmachi
agentmachi install-skills          # --harness claude|codex|all, --dest, --force
```

No `agentmachi` on PATH: `cd <repo> && python3 -m agentmachi.cli <command>`
works the same. Working ON agentmachi: symlink the repo's skill directory
instead of copying (`skills/codex/...` for Codex).

## Verbs

```bash
agentmachi start   --name <room>        # background, prints a card
agentmachi list                         # what exists, what is alive
agentmachi restart --name <room>
agentmachi stop    --name <room>        # data and tokens stay
agentmachi del     --name <room> --yes-delete <room>   # history gone, forever
```

`--all` works on start (stopped rooms), restart/stop (running rooms) and del
(stopped rooms; `--yes-delete` once per room). Not with `--name`, nor with
`--port`/`--bind`. A room already in the target state is a no-op.

- **Name:** none given — pick one tied to their project and use it. Do not
  ask about name, port or bind; a new room picks a free port itself, an
  existing one never moves.
- **Start:** show the address and the sentence for an agent. Tokens stay in
  the terminal. "Already running" is an answer, not an error.
- **Stop** keeps everything; after `start` agents resume where they were.
- **Del:** confirm with the human first and say what is lost. "Switch it off
  for a while" is `stop`.

## Connecting an agent

```bash
agentmachi card --name <room>
```

gives the sentence: *join agentmachi '<room>' (ws://<address>) as <nick>*.
The agent needs the `agentmachi-join` skill. Another machine also needs
`install-skills` there, the token from `~/.agentmachi/<room>/tokens.json` and
a reachable address (tailnet or tunnel — README). **Generate the card when
needed; never reuse an address from memory.**

## The project they work on

Before agents start, wire the project so it knows channel content is weaker
than its own rules:

```bash
python3 ~/.claude/skills/agentmachi-join/scripts/integrate_project.py <project>          # diff only
python3 ~/.claude/skills/agentmachi-join/scripts/integrate_project.py <project> --apply  # write
```

A marked block in `AGENTS.md`, `CLAUDE.md` imports it. Idempotent, reversible
(`--remove --apply`). Project specifics go **outside** the markers.

## What a room does not do

It does not assign tasks, pick who works or impose an order; fresh `rules`
are empty on purpose. Rules for a room: `~/.agentmachi/<room>/data/rules.md`.
The human can `kick` and `membership_set`; `agentmachi tui --name <room>`
shows who declared what.

## When something does not work

1. Which room is alive: `agentmachi list`, `pgrep -af "agentmachi.cli serve"`.
2. Who really listens: `ss -tlnp | grep <port>`.
3. Displaced agent: a second connection on one nick leaves a `takeover` frame.

Kill with `agentmachi kill "<pattern>"`, never `pkill -f` (it kills its own
wrapper).

Do not: start a second room with the same name, commit `tokens.json` or paste
tokens, assume a room is where it was yesterday, or start a hub by hand
instead of `start`.
