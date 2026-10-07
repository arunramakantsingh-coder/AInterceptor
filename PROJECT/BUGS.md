# BUGS.md

## Open
| ID | Severity | Phase | Title | Status |
|---|---|---|---|---|
| B008 | (auto) | (auto) | opened by 3540f02 | Open |
| B006 | (auto) | (auto) | opened by 69fbb8f | Open |
| B001 | Medium | chatgpt | 1 | `atest chatgpt` connects but no reply — session OK, reply extraction failed | Open |
| B009 | (auto) | (auto) | opened by 9d15018 | Open |
| B010 | (auto) | (auto) | opened by 142a6df | Open |
| B011 | (auto) | (auto) | opened by 5cb0731 | Open |
| B012 | (auto) | (auto) | opened by 9a9e737 | Open |
| B013 | (auto) | (auto) | opened by 75126ac | Open |
| B014 | (auto) | (auto) | opened by 753efb3 | Open |
| B015 | (auto) | (auto) | opened by 7d6851c | Open |
| B016 | (auto) | (auto) | opened by 35a8604 | Open |

## Resolved
| ID | Severity | Phase | Title | Resolution |
|---|---|---|---|---|
| B001 | Medium | 0 | PowerShell here-string bootstrap broke mid-run | Migrated to Python bootstrap |
| K002 | Low | 0 | datetime.utcnow() deprecation warning in validate_phase.py | Patched to datetime.now(datetime.UTC) |
| K003 | High | 1.1 | next@15.0.3 CVE-2025-66478 | Bumped to 15.0.7 |

## Regression
| ID | Title | Test That Should Catch |
|---|---|---|
