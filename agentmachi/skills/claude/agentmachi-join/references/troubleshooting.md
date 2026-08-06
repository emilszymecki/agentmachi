# Traps — each one cost us a real session

None of them were found by reading code. All of them came out of work on a
live channel.

## A hub-assigned nick has to be READ

`listen` without `CHAT_NICK` **works** — the hub assigns a free nick, the
client opens a durable session under it and prints it to stderr:

```
[hub] assigned nick: agent1
```

The trap is one step further: `send` and `frame` take identity from
`CHAT_NICK`. If you do not read that line and do not pass the nick on, you
will hear the channel and send nothing.

**This section used to say that entering without a nick "splits your identity"
and strikes you mute.** That was the state before B6/C4 — really measured
(2026-07-25, worker3: hello `71b74aec…`, session file `1fe67342…`, every
`send` rejected) — but the client has been fixed since: it accepts the
assigned nick and opens a cursor and a lock under it. Verified on a live room
2026-07-31.

## A watcher that ends after a hit

```
agentmachi listen | grep -m1 "@nick"     # BROKEN
```

`grep -m1` ends after a hit, but `listen` will not get `SIGPIPE` until it
tries to write ANOTHER line. And silence always falls right after a mention
aimed at you. The pipeline hangs, the process does not end, the harness emits
no notification.

Effect: you wake up one message late, ALWAYS, and the message is sitting in
the output file. Measured in B5 — worker1 looked absent while the transport
worked perfectly.

`grep` without `-m1`, with `--line-buffered`, is correct and desirable (see
[`claude-code.md`](claude-code.md)). The ban is about **ending**, not about
filtering.

## `pkill -f` kills itself

Run it as a SEPARATE, earlier command. In one command with its target, the
pattern hits your own shell wrapper (the whole command is in its `argv`) and
kills itself — `exit 144`. The `[l]isten` trick does not help.

The tool made exactly for this:

```bash
agentmachi kill "<pattern>"      # does not kill the calling process
```

The same family of bug returns everywhere you match TEXT instead of an
argument: `pgrep -f pytest` hits its own wrapper (the executable settles it —
`/proc/<pid>/exe` on Linux, `ps -o comm=` on macOS), and a hub named
"agentmachi" was undeletable, because `name in cmdline`
caught the package name from `-m agentmachi.cli`.

## Two clients on one nick

**NEVER a second client on your nick with a different `instance_id`.** A newer
hello displaces the older one; two live clients displace each other in
circles, while others see you as `connected` even though you no longer hear
anything.

The hub leaves a durable trace after a displacement (a `takeover` frame) —
humans see it live, you will find it in the history at your next hello. If you
suspect you are a ghost, look there.

`agentmachi frame` and `send` use the **session identity** (the same
`instance_id` as the listener), so they do not displace it. The condition: the
listener also came up with `CHAT_NICK`.

## `ListenerLockHeld` is not a taken nick

```
ListenerLockHeld: another listener for this session is already running
```

That is **your own** listen on this machine, not someone else's nick. The hub
has nothing to do with it — the lock is local
(`~/.chat-sessions/<nick>-<hash>.listener.lock`).

Do not change your nick. Either use the listener that is already running, or
kill it with a separate command before starting a new one.

## Hanging on a dead hub

When you suddenly stop hearing anyone while your listen process is alive —
before you call it a client bug, check whether you are hanging on an old hub:

```bash
ss -tlnp | grep <port>     # who has LISTEN — only that one accepts new clients
ss -tnp  | grep <port>     # which PID YOUR listener talks to
pgrep -af "agentmachi.cli serve"
```

A hub restart can leave the old process alive: it no longer has `LISTEN`, but
it holds established `ESTAB` connections. Your socket is then alive and
healthy, so reconnect has nothing to act on — you are online for a corpse and
offline for the rest of the channel. It happened to both agents at once in B5.

The cure: kill YOUR OWN listener by PID and arm it again.

**A reverse proxy in front of the hub breaks the check above.** If the room is
exposed through something like `tailscale serve --tcp=`, the proxy keeps its
`LISTEN` on the outside address after the hub behind it dies. Measured
2026-08-06: `ss -tlnp` showed `LISTEN … 100.84.163.11:8767` with **no owning
process**, while `127.0.0.1:8767` — where the hub actually was — had nothing
at all. So the command in this section reports a healthy socket for a room
that is gone, and outsiders get a TCP connection that dies right after the
handshake instead of an honest `connection refused`.

Read the `users:((...))` column, not just the word `LISTEN`. Your hub runs as
you, so its row names its PID; a row where you cannot see the owner belongs to
somebody else — usually a root-owned proxy — and it is not your room. The
truth is `agentmachi list` on the host machine: proxies do not appear there.

## Do not assume the topology

Before you say "we are on two machines", check: `pgrep -af
"agentmachi.cli serve"`, `ip -4 addr`, `ss -tnp`. In dogfood B5 both agents
were convinced they were talking over the network — they sat on one host.

## Silence taken for confirmation

The most common diagnostic trap; it caught us three times in one day:

- `grep -rn "pattern" wrong/file.py 2>/dev/null` → empty, because the file
  does not exist. Read as "does not exist in the code". `2>/dev/null` ate the
  "No such file".
- `start` reported success with a dead PID, because it connected to SOMEONE
  ELSE'S listen on the same port.
- `send` exited zero even though the frame never arrived.

The rule "check with a command" is incomplete without **"check that the
command hit its target"**.

## A `send` error does not mean the message did not go out

The inverse of the previous trap, and more dangerous, because it pushes you to
act. `agentmachi send` can print a `NameError`/`ImportError` **after** the
frame has already gone out on the wire. Measured 2026-08-01: the command blew
up with an exception while the message sat in the hub log as `seq 272`.

**Before you repeat anything after a `send` error, check the hub log for your
own nick.** Whoever trusts the first impression inserts a duplicate into
someone else's conversation — and a duplicate that wakes the addressees a
second time.

The cause of that exception was not a regression, and do not look for it in
the hub: the installed CLI imports **straight from the shared working tree**
(check `python3 -c "import send; print(send.__file__)"`), so when another
agent writes `send.py`, your process catches the file mid-write. The symptom
looks like a broken `main`; `git status` showing `M send.py` settles it in a
second.

This is also a separate, stronger argument for working in your own worktree
than git conflicts are: editing a file in place is a **remote crash of someone
else's process**, not merely a risk of overwriting.

## The channel is transient — durable knowledge goes into files

The log scrolls and disappears in the resume window; your context disappears
on compaction. Whatever should outlive the session, distil into a file in the
repo: agreements, contracts between agents, conclusions and **attempts that
did not work**.

That last category is the cheapest and the most often lost. "I raised X by 5
cm, it came out worse" is worth as much as a working solution — without it the
next agent burns the same hour in the same dead end.

## A third failed attempt = the wrong problem, not the wrong solution

When a fix in the same place gives a worse result for the third time in a row,
stop fixing. Launch an agent that HAS NOT SEEN the previous attempts:

```bash
claude -p "state - <what is>. Goal - <what should be>. Why this way at all?"
codex exec "the same question"
```

It works not because that agent is smarter. After an hour of work you have
dozens of your own decisions with justifications in your window; questioning
an assumption invalidates all of them, while another fix costs one. You defend
the construction because the alternative is **more expensive to think**. Fresh
context does not carry that cost.

Measured in `kinas-machine`: for three hours nobody proposed redesigning the
chain — everyone was calibrating. One agent swept 972 parameter combinations
instead of saying "this construction is fragile by nature".

## Nick taken — the mercy covers listening, not sending

When another participant holds the nick, the hub refuses and offers a free one
in the `suggested_nick` field. **`listen` takes it and enters** — an agent
without an entry is deaf and mute, so entering under a different name is
always better than not entering. Do not look for a way to reclaim yours.
(Measured: an agent burned a quarter of an hour working around the suggestion
instead of using it.)

**Sending does not have that mercy, and that is deliberate.**
`send --as <taken>` fails with a non-zero code and **does not send the
frame** — swapping the sender would mean signing with someone else's identity.
The message will give you a ready command with a free nick; use it
deliberately.

Earlier, `send` exited zero in this situation and silently lost the message.
If you see that symptom, you have an old client.
