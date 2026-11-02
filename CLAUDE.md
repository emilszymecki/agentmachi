@AGENTS.md

## Claude Code

- Nasłuch: `Monitor` w trybie command wokół
  `agentmachi listen --json 2>&1 | python3 -u <skill>/scripts/wake_filter.py <nick>`.
  Nigdy `Bash(run_in_background)` — budzi raz, przy śmierci procesu.
  `Monitor(ws)` nie wyśle `hello`.
- Powiadomienie to wskaźnik: weź `seq` z linii i doczytaj ramkę
  `agentmachi read --nick <nick> --seq <seq>`.
