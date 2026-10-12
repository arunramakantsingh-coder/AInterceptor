# CLI — Command Surface

Status: Living document. Update in place. Never recreate from scratch.
Last updated: 2026-10-03

Every command is a wrapper in ~/bin/ calling
`python -m scripts.<module>` in ~/ainterceptor with venv + .env loaded.

The /dashboard/commandline page reads backend/app/api/command_tree.py
and renders every entry below. New commands land in the tree in the
same commit that adds the wrapper.

Legend:  ✅ built  🟡 built, not fully verified  🔵 planned  ⚪ future

## Status & Health

  ✅ astatus        Daemon PID, CDP, Xvfb, vnc, tabs, env flags
  ✅ ahealth        Pretty-print /health
  ✅ aversion       Version info
  ✅ aprobe         Read-only provider health
  ✅ atest          Send real message, measure reply
  🟡 amonitor       Live dispatcher probe board
  🟡 atrace         Last N path attempts
  🟡 adispatch      Force a path, trace step by step
  🔵 aint           Full system snapshot
  🔵 apath <id>     Cisco-style trace of one request
  🔵 alive <p>      Live view of an in-flight request

## Daemon Lifecycle

  ✅ astart         Start daemon (background)
  🔵 astart --fg    Start in foreground
  ✅ arestart       Restart
  🔵 arestart --fg  Restart in foreground
  ✅ astop          Stop daemon + Chrome
  🔵 areload        Reload code without stopping Chrome

## Chat

  ✅ chatgpt/claude/gemini/deepseek  Interactive REPL
  🔵 <provider> --via-dispatch       Route through /internal/dispatch
  🔵 <provider> --path A|B           Force transport (debug)
  🔵 aq "<prompt>"                   One-shot send, print reply
  🔵 aq --json "<prompt>"            One-shot, JSON response

## Providers

  ✅ aproviders list/enable/disable/status/validate/info/add/remove/test

## Sessions

  ✅ alogin / alogout / ashow / ahide / asessions
  🔵 asessions refresh

## Configuration

  ✅ aconfig show/list/get/set
  ✅ aconfig-reset <key>

## API Keys

  ✅ akeys list/create/current/revoke
  ⚪ akeys rotate
  ⚪ akeys reveal (impossible — one-way hash)

## Logs & Evidence

  ✅ alogs daemon|chrome|x11vnc
  ✅ aevidence list/show/clear

## Bootstrap & Git

  ✅ abootstrap
  ✅ asave "<msg>"

## Automation

  ✅ asession
  ✅ aprogress
  ✅ sync_docs

## Agent (laptop)

  ✅ airouter-agent connect/login/serve/status

## Shell

  ✅ ashell         Cisco-style interactive shell

## Planned — new subsystems

  🔵 aim serve / list / test
  🔵 ameter app <name> / tenant <id>
  🔵 acredits balance
  🔵 atenant list
  🔵 apolicy show
  🔵 aqlog tail
  🔵 arequests show <id>
  🔵 aexecutions show
  ⚪ aworker list / ping
  🔵 aaccounts list / status / probe / reauth / provision / export / delete
  🔵 atrace --live       Live watch of path_attempts.jsonl
  🔵 adocs list / show <path>

## Command tree metadata

Every entry in command_tree.py must declare:
  category  str    grouping
  desc      str    one line
  syntax    str    usage
  examples  list   realistic examples
  built     bool   True if wrapper exists today

Page and ashell both read this — one source of truth.
