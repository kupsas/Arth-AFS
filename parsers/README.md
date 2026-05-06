# `parsers/` — adding a bank or format

This package holds **readers** that turn bank emails and files into Arth’s internal shapes. In user-facing text, say **import** — not “parse” or “pipeline” (see your editor’s **arth-copy-guidelines** skill for full tone rules).

For the mental model (instrument → provider → account → **import source**), read **[docs/system-design/PARSER_TAXONOMY.md](../docs/system-design/PARSER_TAXONOMY.md)** first.

---

## Pick a sub-package

| You are building… | Put it under… | Registry |
| ----------------- | ------------- | -------- |
| One transaction per email (HTML alert) | `parsers/alerts/` | Wired via `parsers/email_registry.py` + Gmail router |
| Many transactions from a PDF attached to email | `parsers/statements/` | Same |
| Same statement formats, but user uploaded the file | `parsers/uploads/` | `PARSER_REGISTRY` in `parsers/uploads/__init__.py` |
| Holdings / PPF / NPS / broker exports | `parsers/holdings/` | `HOLDING_PARSER_REGISTRY` in `parsers/holdings/__init__.py` |

When two products share the same file layout, they can share one class; when formats differ, split classes even if the provider is the same.

---

## Base classes

- **`parsers/alerts/base.py`** — transaction alert readers (HTML body).
- **`parsers/statements/base.py`** — statement PDFs from email.
- **`parsers/statements/base_broker.py`** — broker-style statement emails (PDF → holdings + trades).
- **`parsers/uploads/base.py`** — files dropped in by the user (website export).
- **`parsers/holdings/base.py`** — portfolio-style uploads.

Extend the right base, register the class in the relevant registry, and add tests under `tests/` with fixtures following `tests/README.md`.

---

## What stays outside `parsers/`

- **`scraper/`** — Gmail OAuth, fetch, routing, scheduler.
- **`pipeline/`** — sorting rules, smart labels, deduplication, `detection.py` for upload type sniffing.

---

## Shims (temporary)

`pipeline/parsers/` and `scraper/email_parsers/` re-export from here so older import paths keep working. Prefer importing from `parsers.*` in new code.
