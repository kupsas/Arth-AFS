#!/usr/bin/env python3
"""
Debug SBI e-account statement PDF unlock during onboarding email import.

Uses the **same** Gmail client, attachment download, password candidate resolver, and
:class:`~parsers.statements.sbi.SBIStatementEmailParser` path as production import.

Typical use (message id from docker logs ``gmail_message_id=…``)::

    # Inside the running API container (same DB + Gmail token as onboarding):
    docker compose exec api python3 scripts/sbi_onboarding_pdf_probe.py \\
        --message-id 182024ef0bc1049c \\
        --user-id local \\
        --show-passwords

    # Compare against a password you know works from manual PDF open:
    docker compose exec api python3 scripts/sbi_onboarding_pdf_probe.py \\
        --message-id 182024ef0bc1049c \\
        --known-password 52568290798 \\
        --show-passwords

On the host (point at the Docker SQLite volume if needed)::

    export ARTH_DB_PATH=/path/to/arth_main.db
    python3 scripts/sbi_onboarding_pdf_probe.py --message-id … --show-passwords

Secrets are printed only with ``--show-passwords`` (local debugging).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pipeline.config  # noqa: E402, F401 — loads ``.env``

import pikepdf  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

from api.constants import DEFAULT_LOCAL_USER  # noqa: E402
from api.database import init_db  # noqa: E402
from api.models import UserSecrets  # noqa: E402
from parsers.statements.sbi import (  # noqa: E402
    SBIStatementEmailParser,
    classify_sbi_statement_subject,
)
from pipeline.config import DB_PATH  # noqa: E402
from scraper.gmail_client import GmailClient  # noqa: E402
from scraper.pdf_passwords import (  # noqa: E402
    ARTH_PDF_INGREDIENT_DOB_ISO,
    ARTH_PDF_INGREDIENT_SBI_MOBILE_LAST5,
    SBI_STATEMENT_PASSWORD_KEYS,
    build_pdf_template_kwargs,
    format_statement_password_unlock_diagnostics,
    resolve_sbi_statement_pdf_password_candidates,
    _derive_password_from_template,
)
from scraper.pdf_utils import decrypt_pdf_with_password_candidates  # noqa: E402
from scraper.secrets_context import resolve_secret_env, statement_secrets_context  # noqa: E402


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "(empty)"
    if len(v) <= 2:
        return "*" * len(v)
    return f"{v[0]}…{v[-1]} (len={len(v)})"


def _load_user_secrets(session: Session, user_id: str) -> dict:
    row = session.exec(select(UserSecrets).where(UserSecrets.user_id == user_id)).first()
    if row is None or not row.secrets_json:
        return {}
    try:
        data = json.loads(row.secrets_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _list_candidates_with_sources(session: Session, user_id: str) -> list[tuple[str, str]]:
    """Mirror ``resolve_sbi_statement_pdf_password_candidates`` but label each source."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in SBI_STATEMENT_PASSWORD_KEYS:
        val = resolve_secret_env(key, "").strip()
        if val and val not in seen:
            seen.add(val)
            out.append((f"env:{key}", val))
    derived = _derive_password_from_template(session, user_id, "sbi_statement")
    if derived and derived not in seen:
        seen.add(derived)
        out.append(("template:sbi_statement", derived))
    return out


def _print_ingredients(session: Session, user_id: str, *, show_passwords: bool) -> None:
    raw = _load_user_secrets(session, user_id)
    kwargs = build_pdf_template_kwargs(session, user_id, raw)
    print("\n── UserSecrets PDF ingredients (user=%r) ──" % user_id)
    print(f"  DB path: {DB_PATH}")
    dob_raw = str(raw.get(ARTH_PDF_INGREDIENT_DOB_ISO, "") or "")
    mob_raw = str(raw.get(ARTH_PDF_INGREDIENT_SBI_MOBILE_LAST5, "") or "")
    if show_passwords:
        print(f"  dob_iso stored:     {dob_raw!r}")
        print(f"  sbi_mobile stored:  {mob_raw!r}")
        print(f"  derived mobile_last5: {kwargs.get('sbi_mobile_last5')!r}")
        print(f"  derived dob_ddmmyy:   {kwargs.get('dob_ddmmyy')!r}")
        expected = f"{kwargs.get('sbi_mobile_last5', '')}{kwargs.get('dob_ddmmyy', '')}"
        print(f"  template password:  {expected!r} (len={len(expected)})")
    else:
        print(f"  dob_iso:     {_mask_secret(dob_raw)}")
        print(f"  mobile key:  {_mask_secret(mob_raw)}")
        print("  (pass --show-passwords to print derived template password)")
    with statement_secrets_context(session, user_id):
        print(
            "  diagnostics:",
            format_statement_password_unlock_diagnostics(session, user_id, "sbi_statement"),
        )


def _print_message_header(client: GmailClient, message_id: str) -> tuple[str, date]:
    msg = client.fetch_message_by_id(message_id)
    print("\n── Gmail message ──")
    print(f"  id:       {msg.id}")
    print(f"  from:     {msg.sender}")
    print(f"  subject:  {msg.subject}")
    print(f"  received: {msg.received_at.isoformat() if msg.received_at else '?'}")
    subj = msg.subject or ""
    ok = classify_sbi_statement_subject(subj)
    print(f"  SBI subject classifier: {'match' if ok else 'NO MATCH'}")
    if not ok:
        print("  warning: onboarding may still route this via sender config, but subject looks unusual")
    recv = msg.received_at.date() if msg.received_at else date.today()
    if msg.received_at and msg.received_at.year < date.today().year - 1:
        print(
            "  note: this is an older statement — if you tested the password on a *newer* "
            "SBI email manually, it may not match PDFs from this year."
        )
    return subj, recv


def _try_decrypt(label: str, pdf_bytes: bytes, candidates: list[str], *, show_passwords: bool) -> bool:
    print(f"\n── Attachment {label} ({len(pdf_bytes):,} bytes) ──")
    if not candidates:
        print("  FAIL — no password candidates")
        return False
    for idx, (source, pw) in enumerate(
        [(f"candidate[{i}]", c) for i, c in enumerate(candidates)],
        start=1,
    ):
        display = pw if show_passwords else _mask_secret(pw)
        print(f"  try #{idx}: {display}")
    try:
        path, used = decrypt_pdf_with_password_candidates(pdf_bytes, candidates)
        used_display = used if show_passwords else _mask_secret(used)
        print(f"  decrypt: OK (used {used_display})")
        path.unlink(missing_ok=True)
        return True
    except pikepdf.PasswordError:
        print("  decrypt: FAIL — none of the candidates unlocked this PDF")
        return False


def _run_parser_path(
    pdf_bytes: bytes,
    candidates: list[str],
    *,
    received: date,
    subject: str,
) -> int:
    """Full production path: SBIStatementEmailParser.parse_attachment."""
    parser = SBIStatementEmailParser({})
    rows = parser.parse_attachment(
        pdf_bytes,
        received,
        email_sender="probe@local",
        email_subject=subject,
    )
    print(f"  parser rows: {len(rows)}")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Debug SBI CAS PDF unlock for one Gmail message")
    ap.add_argument("--message-id", required=True, help="Gmail message id from import logs")
    ap.add_argument("--user-id", default=DEFAULT_LOCAL_USER, help="Arth user_id (default: local)")
    ap.add_argument(
        "--known-password",
        help="Password that works manually — compared to template-derived password",
    )
    ap.add_argument(
        "--show-passwords",
        action="store_true",
        help="Print derived passwords (local debugging only)",
    )
    ap.add_argument(
        "--save-pdf",
        metavar="PATH",
        help="Write the first PDF attachment to this path for manual open in Preview/Adobe",
    )
    args = ap.parse_args()

    init_db()
    engine = create_engine(f"sqlite:///{DB_PATH}")

    client = GmailClient()
    client.authenticate()
    print(f"Gmail: OK | DB: {DB_PATH}")

    subject, received = _print_message_header(client, args.message_id)

    with Session(engine) as session:
        _print_ingredients(session, args.user_id, show_passwords=args.show_passwords)
        with statement_secrets_context(session, args.user_id):
            labeled = _list_candidates_with_sources(session, args.user_id)
            candidates = [pw for _src, pw in labeled]

        print("\n── Password candidates (production resolver order) ──")
        if not labeled:
            print("  (none — save onboarding ingredients or set SBI_STATEMENT_PASSWORD)")
        for src, pw in labeled:
            display = pw if args.show_passwords else _mask_secret(pw)
            print(f"  {src}: {display}")

        with statement_secrets_context(session, args.user_id):
            resolved = resolve_sbi_statement_pdf_password_candidates()
        print(f"  resolve_sbi_statement_pdf_password_candidates() → {len(resolved)} candidate(s)")

        if args.known_password:
            print("\n── Known-password check ──")
            print(f"  known: {args.known_password if args.show_passwords else _mask_secret(args.known_password)}")
            if len(args.known_password) >= 5:
                print(f"  known mobile_last5 guess: {args.known_password[:5]!r}")
            if len(args.known_password) >= 11:
                print(f"  known dob_ddmmyy guess: {args.known_password[5:11]!r}")
            template_pw = next((pw for src, pw in labeled if src == "template:sbi_statement"), "")
            if template_pw and args.known_password:
                if template_pw == args.known_password:
                    print("  template matches known password ✓")
                else:
                    print("  template DOES NOT match known password ✗")
                    if args.show_passwords:
                        print(f"    template: {template_pw!r}")
                        print(f"    known:    {args.known_password!r}")

    atts = client.get_attachments(args.message_id)
    if not atts:
        print("\nFAIL — no attachments on this message", file=sys.stderr)
        return 1

    print(f"\n── Attachments ({len(atts)} file(s)) ──")
    for i, (fname, _raw) in enumerate(atts):
        print(f"  [{i}] {fname} ({len(_raw):,} bytes)")

    if args.save_pdf and atts:
        out_path = Path(args.save_pdf)
        out_path.write_bytes(atts[0][1])
        print(f"\nWrote first attachment to {out_path} — try opening it manually with your password.")

    any_ok = False
    for i, (fname, pdf_bytes) in enumerate(atts):
        if not pdf_bytes[:5].startswith(b"%PDF"):
            print(f"\nSkipping [{i}] {fname}: not a PDF")
            continue
        ok = _try_decrypt(f"[{i}] {fname}", pdf_bytes, candidates, show_passwords=args.show_passwords)
        if ok:
            any_ok = True
            with Session(engine) as session:
                with statement_secrets_context(session, args.user_id):
                    _run_parser_path(pdf_bytes, candidates, received=received, subject=subject)

    if args.known_password and not any_ok:
        print("\n── Retry with --known-password only ──")
        for i, (fname, pdf_bytes) in enumerate(atts):
            if not pdf_bytes[:5].startswith(b"%PDF"):
                continue
            if _try_decrypt(
                f"[{i}] {fname} (known only)",
                pdf_bytes,
                [args.known_password.strip()],
                show_passwords=args.show_passwords,
            ):
                any_ok = True

    if not any_ok:
        print(
            "\nNo PDF decrypted. Common causes:",
            "\n  • Password works on a *different* (newer) email than this message id",
            "\n  • Stored DOB/mobile ≠ what SBI used when *this* PDF was issued (older statements)",
            "\n  • SBI_STATEMENT_PASSWORD in .env overrides with a wrong single candidate",
            "\n  • Gmail attachment bytes differ from what your mail app saves (rare — use --save-pdf to compare)",
            sep="\n",
        )
        return 1

    print("\nDone — at least one PDF decrypted with production candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
