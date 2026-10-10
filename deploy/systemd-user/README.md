# AInterceptor systemd user units

Three units own the runtime stack. They start at login and survive
reboot, resume, and crash when `loginctl enable-linger <user>` is on.

## Install (once, after cloning the VM)

    mkdir -p ~/.config/systemd/user
    cp deploy/systemd-user/*.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable ainterceptor-daemon.service
    systemctl --user enable ainterceptor-dsh.service
    systemctl --user enable ainterceptor-redirect.service
    sudo loginctl enable-linger $USER

## What each unit does

- **ainterceptor-daemon** — runs `~/ainterceptor/run-linux.sh` in the
  foreground. That script activates the venv, loads `.env`, ensures
  Xvfb :99, then execs `python -m app.runtime.daemon`. Restart=always.
  This is the process that owns Chrome, CDP, provider tabs, the
  exporter, the FastAPI app on :8000.

- **ainterceptor-dsh** — starts the DeepSeek Harness on :3080 by
  calling `~/bin/dsh-start`, which writes the current token URL to
  `~/deepseek-harness/dsh-url.txt`. Type=oneshot; dsh itself is a
  background process. Requires ainetceptor-daemon.

- **ainterceptor-redirect** — a tiny HTTP server on :3081 that 302s
  to whatever URL is currently in `dsh-url.txt`. Tailscale Serve
  exposes it at `/harness` on the public hostname. Restart=always.

## Operate

    systemctl --user status  ainterceptor-daemon
    systemctl --user restart ainterceptor-daemon
    systemctl --user stop    ainterceptor-dsh
    journalctl --user -u ainterceptor-daemon -n 100

    # legacy dev helpers still work but bypass systemd:
    arestart                 # pkill + astart (not systemd-managed)
    astop
    # Do not mix arestart and systemctl --user start. Pick one.
