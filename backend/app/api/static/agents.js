
// AInterceptor — agents page helper detection + one-click login
(function () {
  // The agent picks the first bindable port in this range (Windows often
// reserves 45231 for Hyper-V/WSL/Docker). We probe them until one answers.
const AGENT_PORTS = [];
for (let p = 45231; p <= 45241; p++) AGENT_PORTS.push(p);
let AGENT = null;  // set by findAgent() once a port responds

async function findAgent() {
  for (const port of AGENT_PORTS) {
    const url = "http://127.0.0.1:" + port;
    try {
      const r = await fetch(url + "/status", { cache: "no-store" });
      if (r.ok) { AGENT = url; return url; }
    } catch (e) { /* try next */ }
  }
  return null;
}

// Track whether the local agent responded to the last health check.
// If a user clicks Login without the agent running, we show the
// install command instead of failing silently.
let AGENT_ALIVE = false;
const AGENT_NOT_RUNNING_MSG =
  'The local agent is not running on this machine. ' +
  'Install it with: pip install --upgrade "git+https://github.com/arunramakantsingh-coder/AInterceptor.git@fix/cli-chat-provider-gate-cisco-shell#subdirectory=agent" ' +
  'then start it with: airouter-agent serve';

window.agentNotRunning = function () {
  alert(AGENT_NOT_RUNNING_MSG);
  return false;
};

  function el(id) { return document.getElementById(id); }

  function setDot(ok, titleText, detailText) {
    const dot = el("agent-dot");
    if (!dot) return;
    dot.style.color = ok ? "#4ade80" : "#f87171";
    el("agent-title").textContent = titleText;
    el("agent-detail").textContent = detailText;
    el("agent-help").style.display = ok ? "none" : "block";
    // Keep Login buttons visible at all times. If the agent is down,
    // the click handler shows the install command instead of failing.
    document.querySelectorAll(".agent-run").forEach(b => {
      b.style.display = "inline-block";
    });
  }

  async function checkAgent() {
    try {
      const r = await fetch(AGENT + "/status", { cache: "no-store" });
      const d = await r.json();
      if (d.ok) {
          AGENT_ALIVE = true;
        const serverOk = d.server_reachable ? "server reachable" : "server unreachable";
        setDot(true, "Agent running on " + (d.hostname || "this laptop"),
                    d.os + " · " + serverOk + " · " + (d.has_token ? "device token set" : "not connected"));
      } else {
        AGENT_ALIVE = false; setDot(false, "Agent not responding", "Run `airouter-agent serve` on your laptop.");
      }
    } catch (e) {
      AGENT_ALIVE = false; setDot(false, "No local agent found", "Run `airouter-agent serve` on your laptop.");
    }
  }
  window.checkAgent = checkAgent;

  // Copy buttons
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

  // Run buttons
  document.querySelectorAll(".agent-run").forEach(btn => {
    btn.addEventListener("click", async () => {
      const provider = btn.getAttribute("data-provider");
      const out = document.querySelector('.agent-output[data-provider="' + provider + '"]');
      if (out) { out.style.display = "block"; out.textContent = "Starting…"; }
      btn.disabled = true;
      try {
        if (!AGENT_ALIVE) { window.agentNotRunning(); return; }
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

  // Fire on page load
  checkAgent();
  // Keep status fresh
  setInterval(checkAgent, 5000);
})();
