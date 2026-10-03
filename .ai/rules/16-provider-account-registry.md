# R-Provider-Account-Registry

Provider accounts are AIF-owned resources, held in a Registry (Postgres)
and a Vault (encrypted session state). No user sees them. No user links
an account. Model 1 (Application Intelligence) only.

Three-layer subsystem:
  Registry      - inventory: provider, status, capacity, quota, health,
                  region, expiry
  Vault         - encrypted cookies, localStorage, IndexedDB, tokens
                  (AES-GCM per account)
  SessionManager- health loop, rotation engine, re-auth queue

Monitoring cadence:
  Light expired-cookie check: every 15 min
  Real navigate+verify:       every 1 h
  Full send-ping-verify:      on demand (aaccounts probe --full)

Routing: sticky (same AIF session -> same account) -> capacity-weighted
within the sticky pool -> relocate if sticky dead.

Deferred until after AIN is fast and harness is integrated.
