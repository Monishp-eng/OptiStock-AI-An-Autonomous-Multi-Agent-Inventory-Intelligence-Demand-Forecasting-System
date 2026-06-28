"""
suppliers_router.py — Supplier directory CRUD
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.database import get_db
from src.auth import get_current_user

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])


class SupplierBody(BaseModel):
    name: str
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    whatsapp_number: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    notes: Optional[str] = ""


def _clean_phone(phone: str) -> str:
    """Strip all non-digit characters for wa.me links."""
    return "".join(c for c in (phone or "") if c.isdigit())


def _row_to_dict(row) -> dict:
    d = dict(row)
    wa_phone = _clean_phone(d.get("whatsapp_number") or d.get("phone") or "")
    d["wa_link"] = f"https://wa.me/{wa_phone}" if wa_phone else None
    return d


@router.get("")
def list_suppliers(db=Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    rows = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return {"suppliers": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=201)
def create_supplier(body: SupplierBody, db=Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Supplier name is required.")
    now = datetime.utcnow().isoformat()
    cur = db.execute("""
        INSERT INTO suppliers (name, contact_person, phone, whatsapp_number,
                               email, address, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (body.name.strip(), body.contact_person, body.phone,
          body.whatsapp_number, body.email, body.address, body.notes, now))
    db.commit()
    row = db.execute("SELECT * FROM suppliers WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


@router.get("/{supplier_id}")
def get_supplier(supplier_id: int, db=Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    row = db.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return _row_to_dict(row)


@router.put("/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierBody, db=Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    existing = db.execute("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    db.execute("""
        UPDATE suppliers SET name=?, contact_person=?, phone=?, whatsapp_number=?,
            email=?, address=?, notes=? WHERE id=?
    """, (body.name.strip(), body.contact_person, body.phone,
          body.whatsapp_number, body.email, body.address, body.notes, supplier_id))
    db.commit()
    row = db.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    return _row_to_dict(row)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db=Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    existing = db.execute("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    db.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    db.commit()
