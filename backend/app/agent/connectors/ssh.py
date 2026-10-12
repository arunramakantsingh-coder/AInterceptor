"""SSH connector: reaches a remote target via the system ssh client.

Uses the VM's ~/.ssh/id_* key and ~/.ssh/config. Key material never
leaves the OS — the connector shells out to the ssh binary, which
handles auth, known_hosts, and multiplexing.

Interface matches local.LocalConnector: read / write / glob / shell.

All remote shell commands run through the target's login shell.
For Windows targets the DefaultShell should be set to PowerShell
(done on Windows via HKLM\\SOFTWARE\\OpenSSH\\DefaultShell).
"""
from __future__ import annotations
import shlex
import subprocess


class SSHConnector:
    def __init__(self, target):
        self.target = target
        self.host = target.address
        self.user = target.user or "root"

    # ── internals ───────────────────────────────────────────────
    def _ssh(self, remote_cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        """Run one remote command. Returns (rc, stdout, stderr)."""
        full = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=accept-new",
            f"{self.user}@{self.host}",
            remote_cmd,
        ]
        try:
            r = subprocess.run(
                full, capture_output=True, text=True, timeout=timeout,
            )
            return r.returncode, r.stdout or "", r.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", f"timeout after {timeout}s"
        except FileNotFoundError:
            return 127, "", "ssh: binary not found on the VM"
        except Exception as e:
            return 1, "", f"{type(e).__name__}: {e}"

    # ── public interface ────────────────────────────────────────
    def shell(self, cmd: str, timeout: int = 60) -> str:
        rc, out, err = self._ssh(cmd, timeout=timeout)
        result = out
        if err:
            result += ("\n[stderr]\n" + err) if result else err
        if rc != 0:
            result += f"\n[exit code: {rc}]"
        return result.strip() or "(no output)"

    def read(self, path: str) -> str:
        # Windows-safe read: use Get-Content on Windows targets so a
        # path with spaces or backslashes works. Detect by user@host
        # shell probe is too costly; instead send a portable command
        # that works in both bash and PowerShell.
        # bash: cat -- "path"
        # powershell: Get-Content -LiteralPath "path" -Raw
        # The 'cat' alias does not exist in PowerShell; the safest
        # cross-platform read is to send both and let the shell pick.
        win_cmd = f"Get-Content -LiteralPath '{path}' -Raw -ErrorAction Stop"
        nix_cmd = f"cat -- {shlex.quote(path)}"
        # Try Windows shape first (safe no-op on bash: command not found),
        # then fall back to POSIX shape.
        cmd = f"{win_cmd} 2>$null; if ($LASTEXITCODE -ne 0) {{ {nix_cmd} }}"
        # Simpler: try one, then other; pick whichever returns content
        rc1, out1, _ = self._ssh(win_cmd)
        if rc1 == 0 and out1:
            return out1
        rc2, out2, err2 = self._ssh(nix_cmd)
        if rc2 == 0:
            return out2
        return f"error reading {path}: {err2 or out1 or 'unknown'}"

    def write(self, path: str, content: str) -> str:
        # Two shapes again: PowerShell Set-Content, or POSIX tee.
        win_cmd = (
            f"Set-Content -LiteralPath '{path}' -Value @'\n"
            f"{content}\n'@ -Encoding UTF8"
        )
        nix_cmd = (
            f"cat > {shlex.quote(path)} << 'AINT_EOF'\n"
            f"{content}\nAINT_EOF"
        )
        rc1, out1, err1 = self._ssh(win_cmd)
        if rc1 == 0:
            return f"wrote {len(content)} bytes to {path}"
        rc2, out2, err2 = self._ssh(nix_cmd)
        if rc2 == 0:
            return f"wrote {len(content)} bytes to {path}"
        return f"error writing {path}: {err1 or err2 or 'unknown'}"

    def glob(self, pattern: str, root: str | None = None) -> list[str]:
        # Windows: Get-ChildItem -Recurse -Filter; POSIX: find
        win_cmd = (
            f"Get-ChildItem -LiteralPath '{root or '.'}' "
            f"-Recurse -Filter '{pattern}' -ErrorAction SilentlyContinue | "
            f"Select-Object -First 500 -ExpandProperty FullName"
        )
        nix_cmd = (
            f"find {shlex.quote(root or '.')} -type f -name "
            f"{shlex.quote(pattern)} 2>/dev/null | head -500"
        )
        rc1, out1, _ = self._ssh(win_cmd)
        if rc1 == 0 and out1.strip():
            return [l for l in out1.splitlines() if l.strip()]
        rc2, out2, _ = self._ssh(nix_cmd)
        if rc2 == 0 and out2.strip():
            return [l for l in out2.splitlines() if l.strip()]
        return []
