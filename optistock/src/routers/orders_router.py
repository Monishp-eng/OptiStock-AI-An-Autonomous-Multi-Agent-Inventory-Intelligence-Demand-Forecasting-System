"""
orders_router.py — Purchase order CRUD with status lifecycle
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.database import get_db
from src.auth import get_current_user

router = APIRouter(prefix="/api/orders", tags=["Orders"])

VALID_STATUSES = ("pending", "sent", "confirmed", "delivered", "cancelled")


class OrderRequest(BaseModel):
    sku: str
    supplier_id: Optional[int] = None
    quantity: int
    unit_cost: float = 0.0
    expected_delivery_at: Optional[str] = None
    notes: Optional[str] = ""


class StatusUpdate(BaseModel):
    status: str


@router.get("")
def list_orders(status: Optional[str] = None, db=Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    query = """
        SELECT o.*, i.product_name, s.name AS supplier_name
        FROM purchase_orders o
        LEFT JOIN inventory_items i ON o.sku = i.sku
        LEFT JOIN suppliers s ON o.supplier_id = s.id
    """
    params = []
    if status:
        query += " WHERE o.status = ?"
        params.append(status)
    query += " ORDER BY o.ordered_at DESC"
    rows = db.execute(query, params).fetchall()
    return {"orders": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_order(body: OrderRequest, db=Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    sku = body.sku.strip().upper()
    item = db.execute("SELECT sku FROM inventory_items WHERE sku = ?", (sku,)).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' not found.")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be > 0.")

    total_cost = body.quantity * body.unit_cost
    now = datetime.utcnow().isoformat()

    cur = db.execute("""
        INSERT INTO purchase_orders
            (sku, supplier_id, quantity, status, unit_cost, total_cost,
             ordered_at, expected_delivery_at, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (sku, body.supplier_id, body.quantity, "pending",
          body.unit_cost, total_cost, now,
          body.expected_delivery_at, body.notes))
    db.commit()

    row = db.execute("""
        SELECT o.*, i.product_name, s.name AS supplier_name
        FROM purchase_orders o
        LEFT JOIN inventory_items i ON o.sku = i.sku
        LEFT JOIN suppliers s ON o.supplier_id = s.id
        WHERE o.id = ?
    """, (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/{order_id}")
def get_order(order_id: int, db=Depends(get_db),
              current_user: dict = Depends(get_current_user)):
    row = db.execute("""
        SELECT o.*, i.product_name, s.name AS supplier_name
        FROM purchase_orders o
        LEFT JOIN inventory_items i ON o.sku = i.sku
        LEFT JOIN suppliers s ON o.supplier_id = s.id
        WHERE o.id = ?
    """, (order_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found.")
    return dict(row)


@router.put("/{order_id}/status")
def update_status(order_id: int, body: StatusUpdate, db=Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid status. Choose from: {', '.join(VALID_STATUSES)}")
    existing = db.execute("SELECT id FROM purchase_orders WHERE id = ?", (order_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found.")
    db.execute("UPDATE purchase_orders SET status = ? WHERE id = ?", (body.status, order_id))
    db.commit()
    return {"id": order_id, "status": body.status}


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db=Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    existing = db.execute("SELECT id FROM purchase_orders WHERE id = ?", (order_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found.")
    db.execute("DELETE FROM purchase_orders WHERE id = ?", (order_id,))
    db.commit()
