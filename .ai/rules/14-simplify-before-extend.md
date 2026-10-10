# R-Simplify-Before-Extend

Add features by removing code, not by adding it. If a feature requires
growing the hot path, it doesn't ship until the hot path shrinks.

New subsystems (AIR, AIO, AIM, billing) stay design-only until a
second consumer exists that needs them.
