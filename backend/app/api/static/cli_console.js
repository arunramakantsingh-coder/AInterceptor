/* AInterceptor CLI console - Cisco IOS/Nexus style helper.
 * Reads the command tree embedded by commandline_ui.py as JSON and offers
 * TAB completion plus '?' syntax help, mirroring ashell on the VM.
 */
(function () {
  "use strict";

  var treeEl = document.getElementById("cmd-tree");
  if (!treeEl) { return; }

  var TREE = {};
  var PROVIDERS = [];
  try { TREE = JSON.parse(treeEl.textContent || "{}"); } catch (e) { return; }

  var provEl = document.getElementById("cmd-providers");
  if (provEl) {
    try { PROVIDERS = JSON.parse(provEl.textContent || "[]"); } catch (e) { PROVIDERS = []; }
  }

  var input = document.getElementById("cmd-input");
  var out = document.getElementById("cmd-out");
  var search = document.getElementById("cmd-search");
  if (!input || !out) { return; }

  function names() {
    return Object.keys(TREE).sort();
  }

  function subsOf(cmd) {
    var n = TREE[cmd];
    if (!n || !n.subcommands) { return []; }
    return Object.keys(n.subcommands).sort();
  }

  function argsOf(cmd, sub) {
    var n = TREE[cmd];
    if (!n) { return {}; }
    if (sub && n.subcommands && n.subcommands[sub] && n.subcommands[sub].args) {
      return n.subcommands[sub].args;
    }
    return n.args || {};
  }

  function valuesOf(spec) {
    if (!spec) { return []; }
    if (spec.type === "choice") { return spec.choices || []; }
    if (spec.type === "provider") { return PROVIDERS; }
    return [];
  }

  /* Parse what has been typed -> [cmd, sub, partial] */
  function state(line) {
    var t = line.split(/\s+/).filter(Boolean);
    var trail = /\s$/.test(line);
    if (!t.length) { return [null, null, ""]; }
    if (t.length === 1 && !trail) { return [null, null, t[0]]; }
    var cmd = t[0];
    var subs = subsOf(cmd);
    if (t.length === 1) { return [cmd, null, ""]; }
    if (subs.length) {
      if (subs.indexOf(t[1]) >= 0) {
        if (t.length === 2 && !trail) { return [cmd, null, t[1]]; }
        return [cmd, t[1], trail ? "" : t[t.length - 1]];
      }
      return [cmd, null, trail ? "" : t[1]];
    }
    return [cmd, null, trail ? "" : t[t.length - 1]];
  }

  /* Valid next tokens, Cisco-style, filtered by what is typed. */
  function nextTokens(line) {
    var st = state(line), cmd = st[0], sub = st[1], partial = st[2], res = [];
    if (cmd === null) {
      names().forEach(function (n) {
        if (n.indexOf(partial) === 0) {
          res.push([n, (TREE[n] || {}).desc || ""]);
        }
      });
      return res;
    }
    var subs = subsOf(cmd);
    if (sub === null && subs.length) {
      subs.forEach(function (s) {
        if (s.indexOf(partial) === 0) {
          res.push([s, (TREE[cmd].subcommands[s] || {}).desc || ""]);
        }
      });
      return res;
    }
    var args = argsOf(cmd, sub);
    Object.keys(args).forEach(function (k) {
      valuesOf(args[k]).forEach(function (v) {
        v = String(v);
        if (v.indexOf(partial) === 0) { res.push([v, args[k].desc || ""]); }
      });
    });
    return res;
  }

  function render(rows, header) {
    var text = (header ? header + "\n" : "");
    if (!rows.length) { text += "  (no matches)"; }
    rows.forEach(function (r) {
      var name = String(r[0]);
      while (name.length < 24) { name += " "; }
      text += "  " + name + (r[1] || "") + "\n";
    });
    out.textContent = text;
    out.scrollTop = 0;
  }

  function replaceCurrentToken(value) {
    var parts = input.value.split(/\s+/).filter(Boolean);
    if (!parts.length) {
      input.value = value + " ";
      return;
    }
    if (!/\s$/.test(input.value)) { parts.pop(); }
    parts.push(value);
    input.value = parts.join(" ") + " ";
  }

  input.addEventListener("keydown", function (ev) {
    if (ev.key === "Tab") {
      ev.preventDefault();
      var rows = nextTokens(input.value);
      if (rows.length === 1) {
        replaceCurrentToken(rows[0][0]);
        out.textContent = "";
      } else if (rows.length > 1) {
        render(rows, "possible completions:");
      } else {
        out.textContent = "  (no completion available)";
      }
      return;
    }
    if (ev.key === "?") {
      ev.preventDefault();
      var t = nextTokens(input.value);
      render(t.length ? t : [["(end of command)", "no further tokens; press Enter to search cards"]],
             "valid next tokens:");
      return;
    }
    if (ev.key === "Enter") {
      ev.preventDefault();
      var q = input.value.trim();
      if (search) {
        search.value = q;
        var evt;
        try { evt = new Event("input", { bubbles: true }); }
        catch (e) { evt = document.createEvent("Event"); evt.initEvent("input", true, true); }
        search.dispatchEvent(evt);
      }
      var found = nextTokens(q);
      out.textContent = "filtered cards for: " + q +
        (found.length ? "\n\nnext tokens: " + found.map(function (r) { return r[0]; }).join(", ") : "");
      return;
    }
    if (ev.key === "Escape") {
      input.value = "";
      out.textContent = "";
      return;
    }
  });

  out.textContent = "Type ? to list commands, or start typing and press Tab.";
})();
