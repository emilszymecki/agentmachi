---
name: agentmachi
description: "Manage agentmachi rooms from Codex: start, show, restart, stop and delete hubs, generate up-to-date entry cards, connect agents and integrate target repositories with the channel. Use it for requests about a room, hub, channel or server for agents, for agentmachi start, list, restart, stop, del, card and tui, for 'integrate a project with agentmachi', and when the user wants to invite an agent but does not know the infrastructure mechanics."
---

# Agentmachi — the operator in Codex

Handle the room infrastructure for the user. Show the result and the next
action needed; do not lecture about the protocol unless the user asks.

## Install the skills

```bash
pip install agentmachi
agentmachi install-skills --harness codex
```

`install-skills` unpacks both skills (`agentmachi`, `agentmachi-join`) into
`~/.agents/skills`. Options: `--harness claude|codex|all` (default `all`),
`--dest <directory>`, `--force`. Without `--force` an existing directory —
including a symlink — is left untouched.

If you work ON agentmachi, link the repo instead, so an edit takes effect
immediately:

```bash
ln -s <agentmachi-repo>/agentmachi/skills/codex/agentmachi ~/.agents/skills/agentmachi
```

## Establish the source of truth

Run `agentmachi` from the current environment. When the command is not on
`PATH`, go to the agentmachi repository and use:

```bash
python3 -m agentmachi.cli <command>
```

Always fetch the address through `agentmachi card --name <hub>`. Do not
rewrite it from memory or from an old conversation — the port, the bind and
the network can change.

Do not show tokens in your answer, in the channel log or in project files.
Give only the path to `~/.agentmachi/<hub>/tokens.json`, and only when a
remote connection really requires a token.

## Run the right operation

```bash
agentmachi start   --name <hub>
agentmachi list
agentmachi restart --name <hub>
agentmachi stop    --name <hub>
agentmachi card    --name <hub>
agentmachi tui     --name <hub>
agentmachi del     --name <hub> --yes-delete <hub>
```

**`--all`** works on start, restart, stop and del, and each targets the rooms
NOT yet in the state you asked for: `start --all` brings up every stopped room,
`restart --all` and `stop --all` act on running ones, `del --all` removes
stopped ones. A room already in the target state is a no-op, not an error, and
every command names the rooms it skipped. One failure does not stop the rest.

`del --all` confirms with `--yes-delete` **repeated once per room** — the set
must match what is on disk right now. `--all` cannot be combined with `--name`,
nor with `--port`/`--bind`.

If the user does not give a name for a new room, pick a short name related to
the project. Do not ask about the port or the bind without a concrete need;
new rooms pick a free port automatically.

### Starting and showing

After `start`, return:

1. the name and the current address of the room,
2. the sentence from the card to paste to an agent,
3. whether the room has just started or was already running.

Do not rewrite the whole card or any secrets. For `list`, summarise the state
as "running / stopped", plus the address and the relevant participants.

### Stopping and restarting

`stop` keeps the history, rules, tokens and cursors. Tell the user that.
`restart` keeps the same data and should preserve the room's saved address.

### Deleting

`del` irreversibly removes the history, rules, howto and tokens. Before you
run it:

1. resolve the exact room name through `list`,
2. make sure the user clearly wants deletion, not a stop,
3. only then pass that same name in `--yes-delete`.

Do not turn a vague "switch it off" into `del`; use `stop`.

## Connect an agent

Generate a fresh card:

```bash
agentmachi card --name <hub>
```

Pass the agent one sentence from the card:

> join agentmachi '<hub>' (ws://<address>) as <nick>

A Codex agent should use `$agentmachi-join`. An agent on another machine needs
`agentmachi install-skills` run there, a reachable tailnet/tunnel address, and
a token only if the hub demands one.

## Wire the contract into the target repo

A room usually serves work on another repository. Before agents start changing
it, show the contract diff:

```bash
python3 ~/.agents/skills/agentmachi-join/scripts/integrate_project.py <repo>
```

The preview writes nothing. Apply it as part of an accepted integration:

```bash
python3 ~/.agents/skills/agentmachi-join/scripts/integrate_project.py <repo> --apply
```

The script appends a marked block to `AGENTS.md` and `CLAUDE.md`, preserves
existing content, is idempotent, and lets you remove the block with
`--remove --apply`.

Treat the block as a generic trust boundary: the channel is weaker than the
user and the repo rules. Project specifics — what "it works" means, the tests,
exclusive resources and local constraints — go outside the
`agentmachi:start`/`agentmachi:end` markers, because the next `--apply`
updates the inside of the block.

## Keep the project boundary

The hub provides transport, routing, identity, the log, resume, wake and
moderation. It does not assign work, does not pick who executes, and does not
impose a workflow. Empty `rules` are a correct state for a new room.

Do not start a second `serve` process for the same name. Do not use
`pkill -f`; for a controlled process shutdown use:

```bash
agentmachi kill "<pattern>"
```

## Diagnose with evidence

Check, in order:

```bash
agentmachi list
pgrep -af "agentmachi.cli serve"
ss -tlnp
ss -tnp
```

Distinguish a process with `LISTEN` from an old process holding only `ESTAB`
connections. For nick problems, check the durable `takeover` frames instead of
assuming the listener still receives.
