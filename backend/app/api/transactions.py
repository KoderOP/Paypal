from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.data.models import Account, Obligation, Transaction
from app.schemas.api import ObligationCreate, ObligationOut, TransactionOut, TransactionPage
from app.services import repository as repo

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    search: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=60),
    direction: str | None = Query(None, pattern="^(in|out)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    origin: str | None = Query(None, pattern="^(sample|user_import|paypal_api|paypal_checkout|unknown)$"),
    db: Session = Depends(get_db),
):
    user = repo.get_primary_user(db)
    q = select(Transaction, Account.origin, Account.environment).join(Account).where(Account.user_id == user.id)
    if origin:
        q = q.where(Account.origin == origin)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(func.lower(Transaction.description).like(like), func.lower(Transaction.merchant).like(like)))
    if category:
        q = q.where(Transaction.category == category)
    if direction == "in":
        q = q.where(Transaction.amount > 0)
    elif direction == "out":
        q = q.where(Transaction.amount < 0)
    count = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(Transaction.posted_on.desc(), Transaction.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return TransactionPage(
        items=[TransactionOut(id=r.id, posted_on=r.posted_on, description=r.description, merchant=r.merchant,
                              category=r.category, amount=r.amount, source=r.source, origin=o, environment=e,
                              origin_label=repo.origin_label(o, e)) for r, o, e in rows],
        total=count, page=page, page_size=page_size,
    )


@router.get("/transactions/categories", response_model=list[str])
def categories(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    return db.scalars(select(Transaction.category).join(Account).where(Account.user_id == user.id).distinct().order_by(Transaction.category)).all()


@router.get("/obligations", response_model=list[ObligationOut])
def list_obligations(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    rows = db.scalars(select(Obligation).where(Obligation.user_id == user.id).order_by(Obligation.due_on)).all()
    return [ObligationOut(id=o.id, title=o.title, category=o.category, amount=o.amount, due_on=o.due_on, notes=o.notes) for o in rows]


@router.post("/obligations", response_model=ObligationOut, status_code=201)
def create_obligation(body: ObligationCreate, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    if body.due_on < repo.today():
        raise HTTPException(422, "due_on must be today or later")
    o = Obligation(user_id=user.id, **body.model_dump())
    db.add(o)
    db.commit()
    return ObligationOut(id=o.id, **body.model_dump())


@router.delete("/obligations/{obligation_id}", status_code=204)
def delete_obligation(obligation_id: int, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    o = db.get(Obligation, obligation_id)
    if not o or o.user_id != user.id:
        raise HTTPException(404, "Obligation not found")
    db.delete(o)
    db.commit()
