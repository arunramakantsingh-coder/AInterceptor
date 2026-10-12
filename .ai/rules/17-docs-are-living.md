# R-Docs-Are-Living

Every doc under PROJECT/, .ai/, docs/ has the status:

    Living document. Update in place. Never recreate from scratch.

Agents must:
  - read the existing file first
  - append or amend with a dated section
  - mark obsolete sections [DEPRECATED - see <new section>]
  - update a `last_updated:` line at the top

Never:
  - delete-and-replace a doc wholesale
  - fork a v2 doc alongside v1
  - create a doc when the content belongs in an existing one

When a script updates a doc, the script must be idempotent (skip if
already present) and must commit with `[docs:<scope>]`.
