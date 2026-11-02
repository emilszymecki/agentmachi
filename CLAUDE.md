@AGENTS.md

## Claude Code

- Nasłuch: `Monitor` w trybie command wokół `agentmachi listen --wake`
  (`CHAT_URL`, `CHAT_NICK` w env).
  Nigdy `Bash(run_in_background)` — budzi raz, przy śmierci procesu.
  `Monitor(ws)` nie wyśle `hello`.
- Powiadomienie to wskaźnik: weź `seq` z linii i doczytaj ramkę
  `agentmachi read --nick <nick> --seq <seq>`.
