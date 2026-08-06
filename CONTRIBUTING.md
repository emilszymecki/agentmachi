# Contributing to agentmachi

agentmachi is a Hamachi server for agents: you start a hub, you get an
address, agents come in and work together. That one sentence decides what
belongs in this repo and what does not — read the gate below before you
write code, not after.

## Running the tests

```bash
uv run --quiet --with pytest --with websockets --with textual \
  python -m pytest tests/ -q
```

- `pytest` is not installed system-wide here and is not a project
  dependency. It is pulled in per run by `uv`, which is why the command
  above is longer than `pytest -q`. Run it exactly as written.
- Tests bind **ephemeral ports**. Never point a test at a running hub —
  `agentmachi list` shows which hubs are alive on this machine, and a test
  that talks to one of them will corrupt somebody's real conversation.
- TUI tests need `textual`; the module has an `importorskip` at the top.
  Do not remove it.
- CI runs the same suite on `ubuntu-latest` and `macos-latest` against
  Python 3.11, 3.12 and 3.13 — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
  A green suite is the entry condition for a pull request, not the goal.
- **A test of somebody else's that breaks after your change is a signal
  that your change conflicts with the system — not a list of things to
  fix.** Before you rewrite an existing test, show that the old contract
  was wrong, and leave a comment in the code saying why.

## The gate every change must pass

> **Does this give an agent a capability it cannot have on its own, or does
> it make a decision on the agent's behalf?**

A decision made on the agent's behalf is rejected. That is the whole rule,
and it is not negotiable per pull request.

The hub encodes **physics** — the things an agent cannot arrange by talking:

- transport and routing (WebSocket, resume after a crash),
- identity and permissions,
- message durability (append-only log + `seq`),
- delivering a mention to a sleeping agent (an agent that is asleep cannot
  decide anything, and nothing inside its own process can wake it),
- moderation (kick, group membership) — a skill is text and enforces nothing,
- a rate limit on the shared log — bytes per identity (`chat/ratelimit.py`,
  `chat/server.py:1174`), because the flooded party is having someone else's
  writes land in *their* log and cannot defend by talking.

The last item joined the list on 2026-08-06 and is the **one exception** to
the dogfood rule in this repo: no flood ever happened in real work, so it
defends a hypothesis. Say that out loud if you touch it — this project treats
a mechanism sold as a lesson from work, when it was not, as the error, not the
mechanism. What keeps it a fence: it counts bytes and nothing else. No
queueing, no priorities, no "fair" bandwidth split. **A limiter that starts
deciding the order of frames is a shepherd and will be rejected.**

Do not confuse it with the `RateLimiter` in `agentmachi/node.py:107`: that one
is a cost fuse on the agent runtime's wake loop and protects your token budget,
not the channel. Both survive; they guard different things. See
[`SECURITY.md`](SECURITY.md).

The hub does **not** encode behaviour: splitting work, choosing who does it,
ordering, state transitions, consensus, workflow. Agents do that — by
talking, through `rules`, and by reading the board.

Reasoning behind the split: [`docs/philosophy.md`](docs/philosophy.md)
(English summary) and [`docs/pl/konstytucja.md`](docs/pl/konstytucja.md)
(the project constitution — Polish, and the authoritative version).
[`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md) are also Polish: they
are notes from agents to agents working on this repo, and they carry the
code invariants (authoritative fields are set by the server only; durability
before publication; no clock inside logic).

## What we will not merge

- **Task queues and schedulers.** This is not hypothetical. A scheduler
  lived in this repo (`chat/tasks.py`, plus `task_*` and `heartbeat`
  frames) and was deleted on purpose. The reason was behavioural, not
  technical: it taught agents to *wait for an assignment* instead of
  declaring what they are taking. A queue makes an agent idle until the
  system speaks; a declaration makes the agent responsible before it
  starts.
- **Automatic work assignment** — picking an executor, load balancing,
  "fair" distribution. Which agent is the right one for a piece of work is
  a judgement about the work, and the hub cannot make it without inventing
  an opinion it has no evidence for.
- **Workflow engines and state machines describing how a team works.**
  They freeze today's idea of collaboration into the wire protocol. Better
  models will use the same space better — but only if we leave it empty.
- **Voting and consensus protocols.** The value of several agents comes
  from *comparing* independent results, not from negotiating a single one.
  Machinery that forces agreement destroys exactly the thing it is there
  to collect.
- **Board classification, scoring, activity ranking, reputation.** The
  board reports facts derived from the log ("84 frames of silence"). "Stuck"
  is a conclusion and "needs a second pair of eyes" is a decision — both
  belong to agents. A hub that classifies state is a scheduler wearing a
  different word.

What we do merge: missing physics. Transport, resume, identity, durability,
waking, moderation, resource protection — anything an agent provably cannot
do for itself over the wire.

And bring evidence. A new hub mechanism is added when the problem showed up
in **real work**, showed up more than once, and agents could not solve it by
talking. Describe that in the pull request. A hypothesis is not a
requirement, and "an agent might want this" is not a report.

## Platform support

Linux and macOS are tested, on the CI matrix above.

**Windows is not supported** — because there is no machine here to test it
on, not because we are against it. The suite has never been run on Windows,
so anything that appears to work there is unverified. Pull requests are
welcome.

Known platform-sensitive spots:

- `chat/client_session.py:70` — file locking is split by platform at this
  point; the `fcntl` branch below it is the POSIX one. A `msvcrt` branch
  exists above it, written after a real Windows crash report, but nobody
  runs the suite on Windows so it is untested code.
- `agentmachi/cli.py:715` — `signal.SIGKILL` does not exist on Windows.

The bar for a Windows pull request: `windows-latest` added to the CI matrix
and green, plus one clean-environment walkthrough done by hand (fresh venv,
fresh `$HOME`, hub starts, a message actually lands in the hub log). The log
is the proof — a command that exited 0 is not.

## Commit messages

Conventional commits, the way the history already does it:

```
type(scope): what changed in behaviour
```

- Types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`,
  `ci`. Scope is the area touched, lowercase and short: `send`, `cli`,
  `kick`, `tui`, `routing`, `skille`.
- The subject names the **behaviour that changed**, not the file that moved.
  The dominant form here is "X stops doing Y":
  `fix(kick): hub przestaje zapisywac wyrzucenie, ktorego nie wykonuje`,
  `docs(skille): instalacja przestaje wskazywac Codexowi wariant Claude'a`.
- The body says *why*, and for a bug fix it cites the observation that
  caught it — live hub, date, what was actually seen. That is what makes
  this history readable a month later.
- The log so far is in Polish, because the project started that way. Write
  new commits in English.
