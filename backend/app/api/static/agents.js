// AInterceptor — agents page: local helper detection + one-click login
(function () {
  // ── ports ────────────────────────────────────────────────────────
  // Windows often reserves 45231 for Hyper-V/WSL/Docker. Try a short
  // range; the first port that answers /status wins.
  const AGENT_PORTS = [];
  for (let p = 45231; p <= 45241; p++) AGENT_PORTS.push(p);
  let AGENT = null;        // e.g. "http://127.0.0.1:45232"
  let AGENT_ALIVE = false;

  const AGENT_NOT_RUNNING_MSG =
    'The local agent is not running on this machine. ' +
    'Install it with: pip install --upgrade ' +
    '"git+https://github.com/arunramakantsingh-coder/AInterceptor.git' +
    '@fix/cli-chat-provider-gate-cisco-shell#subdirectory=agent" ' +
    'then start it with: airouter-agent serve';

  // ── helpers ──────────────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }

  function setDot(ok, titleText, detailText) {
    const dot = el("agent-dot");
    if (!dot) return;
    dot.style.color = ok ? "#4ade80" : "#f87171";
    const t = el("agent-title"); if (t) t.textContent = titleText;
    const d = el("agent-detail"); if (d) d.textContent = detailText;
    const h = el("agent-help"); if (h) h.style.display = ok ? "none" : "block";
    // Keep Login buttons visible always.
    document.querySelectorAll(".agent-run").forEach(b => {
      b.style.display = "inline-block";
    });
  }

  async function findAgent() {
    for (const port of AGENT_PORTS) {
      const url = "http://127.0.0.1:" + port;
      // Windows reserves some ports for Hyper-V/WSL/Docker; firewall
      // DROPS packets on those (not reject), so plain fetch() hangs
      // forever. Abort after 1.5s and try the next port.
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 1500);
      try {
        const r = await fetch(url + "/status",
                              { cache: "no-store", signal: ctrl.signal });
        if (r.ok) { AGENT = url; return url; }
      } catch (e) { /* timeout or network — try next */ }
      finally { clearTimeout(timer); }
    }
    return null;
  }

  // ── status check ─────────────────────────────────────────────────
  async function checkAgent() {
    try {
      const found = await findAgent();
      if (!found) {
        AGENT_ALIVE = false;
        setDot(false, "No local agent found",
                    "Run `airouter-agent serve` on your laptop.");
        return;
      }
      const r = await fetch(AGENT + "/status", { cache: "no-store" });
      const d = await r.json();
      if (d.ok) {
        AGENT_ALIVE = true;
        const port = AGENT.split(":").pop();
        const srv = d.server_reachable ? "server reachable" : "server unreachable";
        setDot(true,
          "Agent running on " + (d.hostname || "this laptop"),
          (d.os || "?") + " · " + srv + " · port " + port +
          " · " + (d.has_token ? "device token set" : "not connected"));
      } else {
        AGENT_ALIVE = false;
        setDot(false, "Agent not responding",
                    "Run `airouter-agent serve` on your laptop.");
      }
    } catch (e) {
      AGENT_ALIVE = false;
      setDot(false, "No local agent found",
                  "Run `airouter-agent serve` on your laptop.");
    }
  }
  window.checkAgent = checkAgent;

  // ── copy buttons ─────────────────────────────────────────────────
  document.querySelectorAll("[data-copy]").forEach(btn => {
    btn.addEventListener("click", () => {
      const txt = btn.getAttribute("data-copy");
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(txt);
      } else {
        const ta = document.createElement("textarea");
        ta.value = txt; ta.style.position = "fixed"; ta.style.left = "-9999px";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (e) {}
        document.body.removeChild(ta);
      }
      const old = btn.textContent;
      btn.textContent = "copied";
      setTimeout(() => { btn.textContent = old; }, 1200);
    });
  });

  // ── login buttons ────────────────────────────────────────────────
  document.querySelectorAll(".agent-run").forEach(btn => {
    btn.addEventListener("click", async () => {
      const provider = btn.getAttribute("data-provider");
      const out = document.querySelector('.agent-output[data-provider="' + provider + '"]');
      if (out) { out.style.display = "block"; out.textContent = "Starting…"; }
      btn.disabled = true;
      try {
        // Re-probe on click in case the agent started after page load.
        if (!AGENT_ALIVE) {
          const found = await findAgent();
          if (!found) {
            if (out) out.textContent = AGENT_NOT_RUNNING_MSG;
            alert(AGENT_NOT_RUNNING_MSG);
            return;
          }
          AGENT_ALIVE = true;
          checkAgent();
        }
        const r = await fetch(AGENT + "/login/" + provider, { method: "POST" });
        const d = await r.json();
        if (!d.job_id) throw new Error(d.error || "no job id");
        await pollJob(d.job_id, out);
      } catch (e) {
        if (out) out.textContent = "Error: " + e.message;
      } finally {
        btn.disabled = false;
        checkAgent();
      }
    });
  });

  async function pollJob(id, out) {
    while (true) {
      await new Promise(r => setTimeout(r, 1500));
      try {
        const r = await fetch(AGENT + "/job/" + id, { cache: "no-store" });
        const d = await r.json();
        if (out) out.textContent = d.output || "(running…)";
        if (d.status === "done" || d.status === "failed") {
          if (out) out.textContent += "\n— " + d.status + " —";
          return;
        }
      } catch (e) {
        if (out) out.textContent += "\n(poll error: " + e.message + ")";
        return;
      }
    }
  }

  // ── start ────────────────────────────────────────────────────────
  checkAgent();
  setInterval(checkAgent, 5000);
})();
