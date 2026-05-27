# Reference

Reference / vendored snippets kept for copy-paste into other scripts. Not imported anywhere in the repo — this folder is intentionally a library of standalone examples, not a shared module.

## Contents

- `openPyXl_Utils.py` — helper routines for `openpyxl`: evaluating simple formula cells (`SUM`, `AVERAGE`, `MIN`, `MAX`), range parsing, etc. Authored by Len Wanger (2016). Known limitations are documented in the docstring (no cross-sheet refs, no named ranges, no circular-reference detection).

## When to use

Copy the function you need into your own script and adapt. If you find yourself reaching for the same snippet repeatedly, consider whether it belongs in the calling script rather than as a shared import — the rest of this repo deliberately avoids cross-script imports.
