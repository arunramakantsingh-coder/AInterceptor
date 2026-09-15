# GOVERNANCE.md

Project-specific rules (never weaker than baseline).

1. Provider isolation — no cross-imports between adapters.
2. Session files never committed.
3. Adapter interface freeze (5 methods). Changes require ADR.
4. Rate-limit floor: 1 req / 2 sec / provider account (Phase 1-3).
5. Legal notice header in every adapter file.
6. Bootstrap scripts use Python (ADR-0005).
