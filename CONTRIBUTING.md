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
- moderation (kick, group membership) — a skill is text and enforces nothing.

Note what is **not** on that list: rate limiting. `chat/server.py` has no
rate limiter — only a 64 KiB frame cap and keepalive, so an authenticated
participant can flood the shared log and nothing stops them. One was written
and measured on 2026-08-06; it lives on the `rate-limit-czeka-na-incydent`
branch and did **not** land on `main`, because
[`docs/pl/konstytucja.md`](docs/pl/konstytucja.md) requires a problem seen in
real work more than once, and no flood has ever happened here. It comes back
when the incident does — write the incident down, do not rewrite the code.

The rule it has to satisfy on the way back — and did satisfy: count bytes and
rank nothing. No queueing, no priorities, no "fair" bandwidth split. **A
limiter that starts deciding the order of frames is a shepherd and will be
rejected.**

Do not confuse any of this with the `RateLimiter` in `agentmachi/node.py:107`:
that one is a cost fuse on the agent runtime's wake loop and protects your
token budget, not the channel. It is not in the hub. See
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

**If you verify anything on Windows, do not use `start`'s exit code as your
criterion.** Measured there on 2026-08-06, while confirming an unrelated fix:
a regression check got `rc=1` from `agentmachi start` and the room was up,
listening, on the right port. Reporting that exit code would have been a
regression report for a regression that did not exist. The cause is the one
already documented above — process detection does not work on Windows, so
`start` cannot confirm its own child and says so by failing. Until that is
fixed, judge by the config and the socket:

```powershell
agentmachi card --name <room>          # what address it believes it has
netstat -ano | findstr :<port>         # whether anything actually listens
```

The same rule the rest of this file applies to `send` applies here: **a
command that exited non-zero is not proof of failure, exactly as exit 0 is
not proof of success.** On this platform both directions lie.

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

## Releasing

There is no publish pipeline and that is deliberate. CI builds the distribution
and runs `twine check` on it — metadata validation, not an upload. The release
itself is three manual commands by the operator:

```bash
uv run --with build python -m build
set -a; . ~/.config/agentmachi/release.env; set +a
uv run --with twine python -m twine upload dist/*
```

**Do not tag releases in git, and do not read the existing tags as releases.**
`v0.2.0` and `v0.3.0` are roadmap milestones from July 2026 (the B3–B7 merges);
`pyproject.toml` says `version = "0.1.0"` at both of them. The package version
line and the tag namespace collided by accident, and the released `0.2.0` on
PyPI has nothing to do with the tag of that name. The published sequence is the
one on PyPI — `git tag` is not a release history here.

The credential lives in `~/.config/agentmachi/release.env`, mode 0600,
**outside the repository on purpose**: an agent working in the tree does not
trip over it during ordinary work, and `git add -f` cannot reach it. That is
placement, not a fence — anything running as the operator can still read it,
and the boundaries table in [`AGENTS.md`](AGENTS.md) says so in those words.

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
- **Language of the message is yours to pick — Polish and English are both
  fine, and mixing them in one log is fine too.** This line used to say
  "write new commits in English"; on 2026-08-10 all 34 commits of the day
  were Polish, no test guarded the rule, and the examples right above it are
  Polish. A rule nothing enforces and nobody follows is not a standard, it is
  a lie about the project — and the operator's call was to keep the door open
  for people who think in their own language. What is NOT optional is the
  part above: the subject names the behaviour, the body says why and cites
  the observation.
