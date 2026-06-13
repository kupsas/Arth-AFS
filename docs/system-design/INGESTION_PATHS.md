# How money gets **into** Arth

**Plain rule:** You can bring transactions in through **Gmail** (transaction alerts and statement PDFs we recognise) **or** by **uploading** files from your bank’s website. Same overlap rules apply everywhere: if the same spend appears twice, we **match** lines instead of duplicating — see `[pipeline/db_writer.py](../pipeline/db_writer.py)` and `[scraper/README.md](../scraper/README.md)` for detail.

For terminology (transaction alerts vs statement emails vs uploads), see **`[PARSER_TAXONOMY.md](PARSER_TAXONOMY.md)`** — the canonical reference for this repo.

---

## Everyday bank transactions

| Source | Gmail lane | Upload lane |
| ------ | ----------- | ----------- |
| HDFC savings | Transaction alerts + statement PDFs | Yearly `.txt` export or PDF statement |
| HDFC cards | Transaction alerts + CC statement PDFs | Monthly CSV or PDF (depends on card) |
| ICICI savings | Transaction alerts + statement PDFs | PDF / exports you add in Settings |
| SBI savings | E-account statement (CAS) PDF | **Not yet** — Gmail only (mobile last-5 + DOB password). Manual upload planned. |

**Historical Gmail catch-up:** use `POST /api/scraper/backfill` or `scripts/scrape_historical.py` when you want older mail folders imported — contributor-facing name; in UI say **importing older email**.

---

## Holdings and broker-style flows

Some investments show up only as **broker exports** or **statement PDFs**; Gmail may complement those files. When both paths cover the same period, follow dedupe behaviour documented next to the relevant reader.

| Source | Gmail lane | Upload lane |
| ------ | ----------- | ----------- |
| ICICI Direct (equity + MF) | Trade confirmations, equity / MF statement PDFs | CSV portfolio exports |
| Zerodha demat (equity + MF) | Monthly demat transaction statement PDF (PAN password) | Console tradebook CSV; demat statement PDF |
| ICICI PPF | PPF band in ICICI bank e-statement | CSV passbook |
| NPS | — | Statement of holding PDF |

---

## Ways to trigger an import

| You… | What runs |
| ---- | --------- |
| Leave the server on | Scheduled Gmail passes |
| Tap “fetch now” / API | One mail cycle |
| Choose a date window | Historical mail import |
| Upload in **Settings** or CLI | File readers + sorting rules |

Holdings-specific flows use `holding_pipeline.py` — see `[pipeline/README.md](../pipeline/README.md)`.

---

## Contributors: where code lives

| Kind of data | Package |
| ------------ | ------- |
| Transaction alert emails (HTML) | `parsers/alerts/` |
| Statement PDFs attached to email | `parsers/statements/` |
| Files uploaded from disk | `parsers/uploads/` |
| Portfolio / PPF / NPS files | `parsers/holdings/` |

Gmail wiring stays in **`scraper/`** (`email_router.py`, orchestrators, scheduler). See **`[parsers/README.md](../../parsers/README.md)`** for how to add a bank.
