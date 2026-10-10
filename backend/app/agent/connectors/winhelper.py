"""Windows Helper connector. Every shell call goes through the tray
dialog on the target. Reads/writes/globs are implemented on top of
shell so they benefit from the same approval flow."""
from __future__ import annotations
from app.agent import approvals


class WinHelperConnector:
    def __init__(self, target):
        self.target = target

    def shell(self, cmd: str, timeout: int = 300) -> str:
        try:
            resp = approvals.request_approval(
                self.target.address,
                command=cmd,
                reason=f"target={self.target.id}",
                timeout=timeout,
            )
        except approvals.ApprovalDenied as e:
            return f"[denied by user] {e}"
        except approvals.ApprovalTimeout as e:
            return f"[timeout] {e}"
        except Exception as e:
            return f"[error] {e}"
        out = resp.get("output") or ""
        ec = resp.get("exit_code")
        if ec not in (0, None):
            out = out + f"\n[exit code: {ec}]"
        return out

    def read(self, path: str) -> str:
        return self.shell(
            f"Get-Content -LiteralPath '{path}' -Raw -ErrorAction Stop"
        )

    def write(self, path: str, content: str) -> str:
        safe = content.replace("'", "''")
        return self.shell(
            f"Set-Content -LiteralPath '{path}' -Value '{safe}' -Encoding UTF8"
        )

    def glob(self, pattern: str, root: str | None = None) -> list[str]:
        base = root or "$env:USERPROFILE"
        out = self.shell(
            f"Get-ChildItem -LiteralPath '{base}' -Filter '{pattern}' "
            f"-Recurse -ErrorAction SilentlyContinue | "
            f"Select-Object -First 500 -ExpandProperty FullName"
        )
        return [l for l in out.splitlines() if l.strip()]
