"""File-based transaction sources: generic transaction CSV, bank statement CSV and the
PayPal Activity report (Activity → Statements → Download). All three normalise into
`NormalizedTransaction`s; the format is auto-detected from the header row.

| format           | required columns                                         | opening balance      |
|------------------|----------------------------------------------------------|----------------------|
| transactions     | date, description, amount [, category, merchant, balance] | user-supplied / balance col |
| bank_statement   | date, narration/description, withdrawal/debit, deposit/credit, balance | inferred from balance |
| paypal_activity  | Date, Name, Type, Status, Currency, Net/Gross, Transaction ID [, Balance] | inferred from Balance |
"""
import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.core.money import money
from app.data.categorize import categorize
from app.data.sources.base import NormalizedTransaction

FileFormat = Literal["transactions", "bank_statement", "paypal_activity"]
FORMAT_SOURCE: dict[str, str] = {"transactions": "csv", "bank_statement": "bank_statement", "paypal_activity": "paypal"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y")
MAX_ROWS = 20000

ALIASES = {
    "date": ("date", "txn date", "transaction date", "value date", "posting date"),
    "description": ("description", "narration", "particulars", "remarks", "details"),
    "amount": ("amount", "amount (inr)", "amt"),
    "debit": ("withdrawal amt.", "withdrawal amount", "withdrawal", "debit", "debit amount", "dr"),
    "credit": ("deposit amt.", "deposit amount", "deposit", "credit", "credit amount", "cr"),
    "balance": ("closing balance", "balance", "running balance", "available balance"),
    "category": ("category",),
    "merchant": ("merchant", "payee"),
    "pp_txn": ("transaction id",),
    "pp_net": ("net",),
    "pp_gross": ("gross",),
    "pp_status": ("status",),
    "pp_type": ("type",),
    "pp_name": ("name",),
    "pp_currency": ("currency",),
}


class CsvValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


@dataclass
class ParsedFile:
    format: FileFormat
    transactions: list[NormalizedTransaction]
    opening_balance: Decimal | None = None
    warnings: list[str] = field(default_factory=list)


def parse_date(raw: str) -> date:
    value = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{raw}'")


def parse_amount(raw: str, allow_blank: bool = False) -> Decimal:
    cleaned = raw.replace("₹", "").replace(",", "").replace("INR", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    if cleaned in ("", "-") and allow_blank:
        return Decimal("0")
    try:
        return money(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount '{raw}'") from exc


def _hash_id(prefix: str, key: str, seen: dict[str, int]) -> str:
    seen[key] = seen.get(key, 0) + 1
    return f"{prefix}-" + hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:20]


class _Table:
    def __init__(self, content: str):
        reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
        if not reader.fieldnames:
            raise CsvValidationError(["The file is empty"])
        self.headers = {h.strip().lower(): h for h in reader.fieldnames if h}
        self.rows = list(reader)
        if len(self.rows) > MAX_ROWS:
            raise CsvValidationError([f"Too many rows (max {MAX_ROWS})"])

    def key(self, field_name: str) -> str | None:
        return next((self.headers[a] for a in ALIASES[field_name] if a in self.headers), None)

    def has(self, *fields: str) -> bool:
        return all(self.key(f) for f in fields)


def detect_format(table: _Table) -> FileFormat:
    if table.has("pp_txn", "pp_status") and (table.has("pp_net") or table.has("pp_gross")):
        return "paypal_activity"
    if table.has("date", "balance") and (table.has("debit") or table.has("credit")):
        return "bank_statement"
    return "transactions"


def _chronological(rows: list[tuple[date, dict]]) -> list[tuple[date, dict]]:
    """Statements may be newest-first; keep file order within a day but make it ascending."""
    if len(rows) > 1 and rows[0][0] > rows[-1][0]:
        rows = list(reversed(rows))
    return rows


def _opening_from_balance(first_amount: Decimal, first_balance: Decimal) -> Decimal:
    return money(first_balance - first_amount)


def _get(row: dict, key: str | None) -> str:
    return (row.get(key) or "").strip() if key else ""


def parse_transactions(t: _Table) -> ParsedFile:
    missing = [f for f in ("date", "description", "amount") if not t.key(f)]
    if missing:
        raise CsvValidationError([f"Missing required column(s): {', '.join(missing)}"])
    out, errors, seen, balances = [], [], {}, []
    for line, row in enumerate(t.rows, start=2):
        try:
            d = parse_date(_get(row, t.key("date")))
            amt = parse_amount(_get(row, t.key("amount")))
            desc = _get(row, t.key("description"))
            if not desc:
                raise ValueError("description is empty")
            if amt == 0:
                raise ValueError("amount is zero")
            bal = _get(row, t.key("balance"))
            balances.append(parse_amount(bal) if bal else None)
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
            continue
        cat = _get(row, t.key("category")) or categorize(desc, amt > 0)
        merchant = _get(row, t.key("merchant")) or desc[:120]
        ext = _hash_id("csv", f"{d}|{desc}|{amt}", seen)
        out.append(NormalizedTransaction(ext, d, desc[:255], merchant[:120], cat[:60], amt))
    if errors:
        raise CsvValidationError(errors)
    opening = _opening_from_balance(out[0].amount, balances[0]) if out and balances and balances[0] is not None else None
    return ParsedFile("transactions", out, opening)


def parse_bank_statement(t: _Table) -> ParsedFile:
    if not t.key("description"):
        raise CsvValidationError(["Missing a narration/description column"])
    dated, errors = [], []
    for line, row in enumerate(t.rows, start=2):
        raw_date = _get(row, t.key("date"))
        if not raw_date:
            continue  # blank / footer lines are common in bank exports
        try:
            dated.append((parse_date(raw_date), {**row, "__line": line}))
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
    if errors:
        raise CsvValidationError(errors)
    out, seen, opening = [], {}, None
    for i, (d, row) in enumerate(_chronological(dated)):
        try:
            debit = parse_amount(_get(row, t.key("debit")), allow_blank=True)
            credit = parse_amount(_get(row, t.key("credit")), allow_blank=True)
            balance = parse_amount(_get(row, t.key("balance")))
        except ValueError as exc:
            errors.append(f"line {row['__line']}: {exc}")
            continue
        amt = money(credit - abs(debit))
        if amt == 0:
            continue
        desc = _get(row, t.key("description")) or "Bank transaction"
        if i == 0 or opening is None:
            opening = _opening_from_balance(amt, balance)
        ext = _hash_id("bank", f"{d}|{desc}|{amt}|{balance}", seen)
        out.append(NormalizedTransaction(ext, d, desc[:255], _merchant_from_narration(desc), categorize(desc, amt > 0), amt))
    if errors:
        raise CsvValidationError(errors)
    return ParsedFile("bank_statement", out, opening)


def _merchant_from_narration(desc: str) -> str:
    # e.g. "UPI/Swiggy/412345/Food order" -> "Swiggy"; otherwise the narration itself.
    parts = [p.strip() for p in desc.replace("-", "/").split("/") if p.strip()]
    if len(parts) >= 2 and parts[0].upper() in {"UPI", "NEFT", "IMPS", "ACH", "POS", "NACH", "ECS"}:
        return parts[1][:120]
    return desc[:120]


def parse_paypal_activity(t: _Table) -> ParsedFile:
    amount_key = t.key("pp_net") or t.key("pp_gross")
    dated, errors, warnings = [], [], []
    skipped = 0
    currencies: set[str] = set()
    for line, row in enumerate(t.rows, start=2):
        status = _get(row, t.key("pp_status")).lower()
        if status and status not in ("completed", "success", "s"):
            skipped += 1
            continue
        try:
            dated.append((parse_date(_get(row, t.key("date"))), {**row, "__line": line}))
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
        cur = _get(row, t.key("pp_currency"))
        if cur:
            currencies.add(cur.upper())
    if len(currencies) > 1:
        errors.append(f"Multiple currencies found ({', '.join(sorted(currencies))}). Export one currency per file.")
    if errors:
        raise CsvValidationError(errors)
    if skipped:
        warnings.append(f"{skipped} non-completed PayPal transaction(s) were skipped.")
    if currencies and currencies != {"INR"}:
        warnings.append(f"Amounts are in {next(iter(currencies))}; FINORA displays them as-is.")

    out, opening = [], None
    for d, row in _chronological(dated):
        try:
            amt = parse_amount(_get(row, amount_key))
        except ValueError as exc:
            errors.append(f"line {row['__line']}: {exc}")
            continue
        if amt == 0:
            continue
        ptype = _get(row, t.key("pp_type")) or "PayPal transaction"
        name = _get(row, t.key("pp_name")) or ptype
        txn_id = _get(row, t.key("pp_txn"))
        if not txn_id:
            errors.append(f"line {row['__line']}: missing Transaction ID")
            continue
        if opening is None and _get(row, t.key("balance")):
            opening = _opening_from_balance(amt, parse_amount(_get(row, t.key("balance"))))
        desc = f"{ptype} · {name}" if name != ptype else ptype
        out.append(NormalizedTransaction(f"pp-{txn_id}", d, desc[:255], name[:120], categorize(f"{name} {ptype}", amt > 0), amt))
    if errors:
        raise CsvValidationError(errors)
    return ParsedFile("paypal_activity", out, opening, warnings)


PARSERS = {"transactions": parse_transactions, "bank_statement": parse_bank_statement, "paypal_activity": parse_paypal_activity}


def parse_file(content: str, fmt: str = "auto") -> ParsedFile:
    table = _Table(content)
    chosen = detect_format(table) if fmt == "auto" else fmt
    if chosen not in PARSERS:
        raise CsvValidationError([f"Unknown format '{fmt}'"])
    parsed = PARSERS[chosen](table)
    if not parsed.transactions:
        raise CsvValidationError(["The file contains no transactions"])
    return parsed
