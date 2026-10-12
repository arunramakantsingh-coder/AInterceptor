"""Permission gate: wrapper peeling + read-only safe list.

Item 2.1. The exploit case: "timeout 5 rm -rf /" must be
judged by "rm", never by "timeout"."""
import pytest

from app.agent import permissions


@pytest.mark.parametrize("cmd", [
    "hostname",
    "timeout 5 hostname",
    "env FOO=1 hostname",
    "nice -n 5 diff a b",
    "nohup jq . file",
    "ionice -c 2 -n 0 curl -s http://x",
    "timeout -k 5 10 curl -s http://x",
    "stdbuf -oL cat file",
    "md5sum file",
    "sha256sum file",
    "stat file",
    "diff a b",
    "file some.bin",
])
def test_gate_allows(cmd):
    decision, _ = permissions.evaluate("shell", {"cmd": cmd})
    assert decision == "allow"


@pytest.mark.parametrize("cmd", [
    "timeout 5 rm -rf /",
    "env X=1 rm -rf /",
    "nice -n 5 rm -fr /",
    "rm -rf /",
    "timeout 5 sed -i s/x/y/ file",
    "timeout 5 awk '{print}' file",
    "timeout 5 ssh host cmd",
    "unknownbin x",
    "timeout 5 unknownbin",
])
def test_gate_asks(cmd):
    decision, _ = permissions.evaluate("shell", {"cmd": cmd})
    assert decision == "ask"


@pytest.mark.parametrize("cmd", ["", "timeout", "env"])
def test_gate_denies(cmd):
    decision, _ = permissions.evaluate("shell", {"cmd": cmd})
    assert decision == "deny"
