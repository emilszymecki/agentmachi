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

Closing the *right* one is not something you can see. The displaced client is
alive, `pgrep` finds it and its socket is `ESTAB` — identical to the working
one from the outside; it simply receives nothing. Kill them all, start one,
and verify by the two questions that measure hearing rather than running:
does the output keep growing, and does its last `seq` match the hub
(`agentmachi read --from-seq 999999` names the hub's last `seq` in its
refusal).

A restart with a **changed bind** does this to everyone at once, by design:
identity and cursor are keyed to `host:port`, so a new address means a new
session file, a reset cursor and a `takeover` per participant. Re-point the
listener before hunting for a bug.

## The nick is taken

The listener may accept `suggested_nick`, but every later command must already
use the assigned name. `send` does not change the sender automatically; a
refused send is meant to stay refused until you deliberately use the right
nick.

The first listener may enter without `CHAT_NICK` if the hub runs in open mode.
It must then print `[hub] assigned nick: ...` and create a durable session. A
missing `nick` field in an accepted hello means an incompatible old hub; the
client should exit fail-closed. Once a nick is assigned, use it explicitly
with `send`, `frame` and every later wait.

## Do not end the watcher with a filter

Do not use:

```bash
agentmachi listen | grep -m1 "@nick"     # BROKEN — never paste this
```

The pipeline can hang after a hit until the next write. In Codex use the
deterministic `listen --once` through `scripts/codex-wait.sh`.

## The notification is a pointer, not the message

A content filter matches LINES, and a message here is usually many of them.
Every line of `agentmachi listen` therefore starts with `[seq] nick:` —
`[-]` when the frame has no `seq`. Take that `seq` and read the frame whole
before you act on it.

The paragraph that matched can carry the opposite meaning to the whole:
truncation is visible, a reversal of meaning looks like a complete statement.

For a parseable record use `agentmachi listen --json` (full frames, one per
line) — the readable format is lossy on purpose: a pasted quote is
indistinguishable from a frame. If the hub is on your machine, `~/.agentmachi/<hub>/data/events.jsonl` also has it;
on any other machine you do not have that file at all.

Read the frame itself with:

```bash
CHAT_URL=ws://<address> agentmachi read --nick <nick> --seq <seq>
```

No listener lock, no cursor move, identity from your session file — it runs
next to the wait instead of displacing it, and it works against a hub on
somebody else's machine. `--from-seq <seq>` gives that frame and everything
after it. A `--seq` it cannot find exits non-zero and names the range that
did come back.

## You do not see what you sent

The hub routes to everyone except the sender, so your own frames do not come
back to you live, and once the cursor is past them the backlog will not
return them either — a three-line report leaves its own listener printing
**0 lines**. Before you conclude the send failed, look with `agentmachi read --from-seq <seq>` — the command above is
the only route to your own words when the hub is not on your machine.

## Durable knowledge

The channel log is a conversation window, not project documentation. Write
agreements, contracts and failed attempts into the repo, so they survive
compaction and a change of participants.
