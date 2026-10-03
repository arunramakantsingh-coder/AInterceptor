
// AInterceptor — agents page helper detection + one-click login
(function () {
  const AGENT = "http://127.0.0.1:45231";

  function el(id) { return document.getElementById(id); }

  function setDot(ok, titleText, detailText) {
    const dot = el("agent-dot");
    if (!dot) return;
    dot.style.color = ok ? "#4ade80" : "#f87171";
    el("agent-title").textContent = titleText;
    el("agent-detail").textContent = detailText;
    el("agent-help").style.display = ok ? "none" : "block";
    document.querySelectorAll(".agent-run").forEach(b => {
      b.style.display = ok ? "inline-block" : "none";
    });
  }

  async function checkAgent() {
    try {
      const r = await fetch(AGENT + "/status", { cache: "no-store" });
      const d = await r.json();
      if (d.ok) {
        const serverOk = d.server_reachable ? "server reachable" : "server unreachable";
        setDot(true, "Agent running on " + (d.hostname || "this laptop"),
                    d.os + " · " + serverOk + " · " + (d.has_token ? "device token set" : "not connected"));
      } else {
        setDot(false, "Agent not responding", "Run `airouter-agent serve` on your laptop.");
      }
    } catch (e) {
      setDot(false, "No local agent found", "Run `airouter-agent serve` on your laptop.");
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
