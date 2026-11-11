"""Data onboarding: status, demo files, file import (transactions / bank statement / PayPal), reset."""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.data.demo_files import DEMO_FILES, is_sample_content, render
from app.data.models import Account, Transaction
from app.data.sources.files import FORMAT_SOURCE, CsvValidationError, parse_file
from app.schemas.api import DemoFileOut, ImportResult, StatusOut
from app.services import repository as repo
from app.services.import_service import MixedProvenanceError, clear_user_data, store_transactions

router = APIRouter(tags=["data"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
FORMATS = ("auto", "transactions", "bank_statement", "paypal_activity")


@router.get("/status", response_model=StatusOut)
def status(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    count = db.scalar(select(func.count(Transaction.id)).join(Account).where(Account.user_id == user.id)) or 0
    prov = repo.provenance(db, user)
    return StatusOut(has_data=count > 0, user_name=user.name, data_source=(user.preferences or {}).get("data_source"),
                     transaction_count=count, provenance=prov, sample_count=sum(p["count"] for p in prov if p["synthetic"]))


@router.get("/demo-files", response_model=list[DemoFileOut])
def demo_files():
    out = []
    for f in DEMO_FILES:
        _, content, opening = render(f.id, repo.today(), get_settings().demo_seed)
        out.append(DemoFileOut(id=f.id, title=f.title, format=f.format, filename=f.filename, description=f.description,
                               suggested_opening_balance=opening if f.format == "transactions" else None,
                               rows=max(0, len([l for l in content.splitlines() if l.strip()]) - 1)))
    return out


@router.get("/demo-files/{file_id}")
def demo_file(file_id: str):
    try:
        meta, content, _ = render(file_id, repo.today(), get_settings().demo_seed)
    except KeyError:
        raise HTTPException(404, "Demo file not found")
    return Response(content,
                    media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{meta.filename}"'})


@router.post("/data/import", response_model=ImportResult)
async def import_file(
    file: UploadFile = File(...),
    format: str = Form("auto"),
    opening_balance: str = Form(""),
    replace: bool = Form(False),
    db: Session = Depends(get_db),
):
    if format not in FORMATS:
        raise HTTPException(422, f"format must be one of {', '.join(FORMATS)}")
    opening: Decimal | None = None
    if opening_balance.strip():
        try:
            opening = Decimal(opening_balance.replace(",", "").strip())
        except InvalidOperation:
            raise HTTPException(422, "opening_balance must be a number")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(422, "File must be a UTF-8 encoded CSV")
    try:
        parsed = parse_file(content, format)
    except CsvValidationError as exc:
        raise HTTPException(422, {"message": "We couldn't read this file", "errors": exc.errors[:20]})

    source = FORMAT_SOURCE[parsed.format]
    user = repo.get_primary_user(db)
    origin = "sample" if is_sample_content(content, file.filename) else "user_import"
    try:
        result = store_transactions(db, user, source, parsed.transactions,
                                    opening if opening is not None else parsed.opening_balance, replace, parsed.format,
                                    origin=origin)
    except MixedProvenanceError as exc:
        raise HTTPException(409, str(exc))
    warnings = list(parsed.warnings)
    if origin == "sample":
        warnings.append("This is FINORA's synthetic sample file, so it's labelled as sample data, not as real records.")
    if opening is None and parsed.opening_balance is None and parsed.format == "transactions":
        warnings.append("No opening balance given — balances start from ₹0. Add a 'balance' column or enter one.")
    return ImportResult(format=parsed.format, source=source, warnings=warnings, **result)


class LoadSample(BaseModel):
    file_id: str = Field("paypal_activity", max_length=40)
    replace: bool = True


@router.post("/data/sample", response_model=ImportResult)
def load_sample(body: LoadSample, db: Session = Depends(get_db)):
    """Load FINORA's fictional sample profile. Generated on the server, so it is always stored as origin='sample'."""
    try:
        _, content, opening = render(body.file_id, repo.today(), get_settings().demo_seed)
    except KeyError:
        raise HTTPException(404, "Sample file not found")
    parsed = parse_file(content, "auto")
    source = FORMAT_SOURCE[parsed.format]
    try:
        result = store_transactions(db, repo.get_primary_user(db), source, parsed.transactions,
                                    parsed.opening_balance if parsed.opening_balance is not None else opening, body.replace,
                                    parsed.format, origin="sample")
    except MixedProvenanceError as exc:
        raise HTTPException(409, str(exc))
    return ImportResult(format=parsed.format, source=source, warnings=[], **result)


@router.delete("/data", status_code=204)
def clear_data(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    clear_user_data(db, user)
    db.commit()
