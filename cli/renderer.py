import sys


def banner() -> None:
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                    A I N T E R C E P T O R                 ║")
    print("║              Web AI Provider Control Plane                 ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()


def providers(specs) -> None:
    print("Providers")
    print("────────────────────────────────────────────────────────────")

    for index, spec in enumerate(specs, 1):
        state = "● CONFIGURED" if spec.configured else "○ NOT CONFIGURED"
        print(f"  [{index}] {spec.display_name:<18} {state}")

    print()


def system_status() -> None:
    print("System")
    print("────────────────────────────────────────────────────────────")
    print("  Interceptor          READY")
    print("  Orchestrator         READY")
    print("  Gateway              READY")
    print()


def global_help() -> None:
    print("""
Global commands:
  help, ?              Show available commands
  providers            List AI providers
  status               Show control-plane status
  use <provider>       Enter provider context
  sessions             Show sessions
  diagnostics          Run diagnostics
  version              Show CLI version
  clear                Clear terminal
  exit, quit           Exit AInterceptor

Provider selection:
  1                    Select Claude Web
  2                    Select ChatGPT Web
  3                    Select Gemini Web
  4                    Select Grok Web

Tip:
  Type part of a command and press TAB to complete it.
""")


def provider_help() -> None:
    print("""
Provider commands:
  help, ?              Show provider commands
  status               Provider status
  session              Session information
  chat                 Start interactive chat
  diagnostics          Provider diagnostics
  doctor               Provider health check
  back                 Return to global context
  exit, quit           Exit AInterceptor

Tip:
  Type part of a command and press TAB to complete it.
""")


def print_stream_delta(delta: str) -> None:
    print(delta, end="", flush=True)


def print_stream_end() -> None:
    print()
    print()


def error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
