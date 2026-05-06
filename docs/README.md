# Docs folder

Design notes, benchmarks, and reference material for Arth — **not** the marketing website.

---

## What lives where


| Folder               | Contents                                                                                                              |
| -------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `**system-design/`** | Active architecture — e.g. **[INGESTION_PATHS.md](system-design/INGESTION_PATHS.md)**, **[PARSER_TAXONOMY.md](system-design/PARSER_TAXONOMY.md)** |
| `**evaluations/**`   | Smart-label benchmarks, methodology, cost/accuracy trade-offs                                                         |
| `**data-notes/**`    | How raw bank formats map into Arth’s shapes                                                                           |
| `**reference/**`     | PDF frameworks (layers map, Day‑1 questions)                                                                          |
| `**archive/**`       | Older scratch notes — useful context, not gospel                                                                      |
| `**product/**`       | Living product specs when present                                                                                     |


Older brainstorm docs sit under `[archive/system-design/](archive/system-design/)`.

---

## Highlights


| File                                                                                         | Why open it                                      |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `[system-design/PARSER_TAXONOMY.md](system-design/PARSER_TAXONOMY.md)`                                                  | Import sources + mental model for `parsers/`       |
| `[system-design/INGESTION_PATHS.md](system-design/INGESTION_PATHS.md)`                       | Gmail vs uploads; where contributors edit code     |
| `[system-design/PARSER_REFACTOR_PLAN.md](system-design/PARSER_REFACTOR_PLAN.md)`             | Parser package layout (PR1/PR2 checklist)            |
| `[evaluations/llm-benchmark-2026-03/README.md](evaluations/llm-benchmark-2026-03/README.md)` | Why today’s single-pass smart-label setup exists |


