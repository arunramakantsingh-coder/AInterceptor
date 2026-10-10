
"""Pretty printer for aidaemon status."""
import json, urllib.request, sys, pathlib

def main():
    try:
        with urllib.request.urlopen("http://127.0.0.1:7700/", timeout=2) as r:
            data = json.loads(r.read())
    except Exception:
        print("aidaemon  ●  not running")
        print("           start with: aidaemon start")
        return 0

    print("aidaemon  ●  running")
    print()
    print(f"  {'PROVIDER':<10} {'PORT':<6} {'BROWSER':<10} {'ATTACHED':<10}")
    print("  " + "-" * 40)
    for name, cfg in data["providers"].items():
        browser = "alive" if cfg["chrome_alive"] else "off"
        attached = "yes" if cfg["attached"] else "no"
        print(f"  {name:<10} {cfg['port']:<6} {browser:<10} {attached:<10}")
    print()
    print("  Browser launches on first use. Login once with:")
    print("     daemon login <provider>")
    print()
    print("  Chat:  deepseek  |  claude  |  chatgpt  |  aigemini")
    return 0

sys.exit(main())
