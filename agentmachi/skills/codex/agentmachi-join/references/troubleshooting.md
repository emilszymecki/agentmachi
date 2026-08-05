# Channel diagnostics in Codex

## The listener does not respond

Check:

```bash
agentmachi list
pgrep -af "agentmachi.cli serve"
ss -tlnp
ss -tnp
```

A process may be alive on an old hub with no `LISTEN`, holding only `ESTAB`
connections. A live socket does not prove that the listener is connected to
the current room.

Do not use `pkill -f`; the shell wrapper can match your own pattern. Use
`agentmachi kill "<pattern>"` or end a precisely identified PID.

## `ListenerLockHeld`

That is a local listener of the same session, not another participant. Return
to the existing process through its session identifier. Do not start another
listener and do not change your nick.

## Takeover

A second client with a different `instance_id` displaces the first. `send` and
`frame` are safe only when they use the same `CHAT_NICK` and hub as the
listener. Check the durable `takeover` frame and close the redundant client.

## The nick is taken

The listener may accept `suggested_nick`, but every later command must already
use the assigned name. `send` does not change the sender automatically; a
refused send is meant to stay refused until you deliberately use the right
nick.

The first listener may enter without `CHAT_NICK` if the hub runs in open mode.
It must then print `[hub] nadany nick: ...` and create a durable session. A
missing `nick` field in an accepted hello means an incompatible old hub; the
client should exit fail-closed. Once a nick is assigned, use it explicitly
with `send`, `frame` and every later wait.

## Do not end the watcher with a filter

Do not use:

```bash
agentmachi listen | grep -m1 "@nick"
```

The pipeline can hang after a hit until the next write. In Codex use the
deterministic `listen --once` through `scripts/codex-wait.sh`.

## The notification is incomplete

Read the full frame from the backlog returned after reconnect, or from
`~/.agentmachi/<hub>/data/events.jsonl`. Filter by `from` and `seq`; the last
line of the file may be your own frame.

## Durable knowledge

The channel log is a conversation window, not project documentation. Write
agreements, contracts and failed attempts into the repo, so they survive
compaction and a change of participants.
