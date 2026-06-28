"""
sales_router.py — Daily sales entry endpoints
"""
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.database import get_db
from src.auth import get_current_user

router = APIRouter(prefix="/api/sales", tags=["Sales"])


class SaleRequest(BaseModel):
    sku: str
    quantity: int
    sale_date: Optional[str] = None  # ISO date string YYYY-MM-DD, defaults to today


@router.post("")
def record_sale(body: SaleRequest, db=Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    """Record a sale and deduct from current_stock."""
    sku = body.sku.strip().upper()

    item = db.execute(
        "SELECT sku, current_stock FROM inventory_items WHERE sku = ?", (sku,)
    ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' not found.")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0.")

    sale_date = body.sale_date or date.today().isoformat()
    now = datetime.utcnow().isoformat()

    db.execute(
        "INSERT INTO daily_sales (sku, quantity, sale_date, created_at) VALUES (?,?,?,?)",
        (sku, body.quantity, sale_date, now),
    )
    # Deduct from current stock (floor at 0)
    new_stock = max(0, (item["current_stock"] or 0) - body.quantity)
    db.execute(
        "UPDATE inventory_items SET current_stock = ?, updated_at = ? WHERE sku = ?",
        (new_stock, now, sku),
    )
    db.commit()

    return {
        "sku": sku,
        "quantity": body.quantity,
        "sale_date": sale_date,
        "new_stock": new_stock,
    }


@router.get("")
def get_sales(
    sku: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List sales records with optional filters."""
    query = """
        SELECT s.id, s.sku, i.product_name, s.quantity, s.sale_date, s.created_at
        FROM daily_sales s
        LEFT JOIN inventory_items i ON s.sku = i.sku
        WHERE 1=1
    """
    params = []
    if sku:
        query += " AND s.sku = ?"
        params.append(sku.upper())
    if from_date:
        query += " AND s.sale_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND s.sale_date <= ?"
        params.append(to_date)
    query += " ORDER BY s.sale_date DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return {"sales": [dict(r) for r in rows]}


@router.get("/summary")
def sales_summary(db=Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    """Per-SKU sales summary: total sold in last 7 and 30 days, avg daily."""
    rows = db.execute("""
        SELECT
            s.sku,
            i.product_name,
            SUM(CASE WHEN s.sale_date >= date('now', '-7 days')  THEN s.quantity ELSE 0 END) AS sold_7d,
            SUM(CASE WHEN s.sale_date >= date('now', '-30 days') THEN s.quantity ELSE 0 END) AS sold_30d,
            ROUND(SUM(CASE WHEN s.sale_date >= date('now', '-30 days') THEN s.quantity ELSE 0 END) / 30.0, 2) AS avg_daily
        FROM daily_sales s
        LEFT JOIN inventory_items i ON s.sku = i.sku
        GROUP BY s.sku
        ORDER BY sold_30d DESC
    """).fetchall()
    return [dict(r) for r in rows]
