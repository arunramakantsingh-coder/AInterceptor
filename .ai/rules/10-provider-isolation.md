# R-Provider-Isolation

One file per provider in `backend/app/interception/<provider>.py`.
Each file declares only:
  name, home_url, login_markers, response_markers,
  composer_selectors, parse(body)->str, pre_send(page), diagnose(page)

The dispatcher never branches on provider name. No "Path A / Path B"
concept anywhere. If a provider is broken, its file says why.

Cost: ~30 KB Python, one-time load. No measurable RAM/CPU overhead.
Savings: removes shared-state bugs, prevents DOM-polling regressions,
keeps fix blast-radius to a single file.
