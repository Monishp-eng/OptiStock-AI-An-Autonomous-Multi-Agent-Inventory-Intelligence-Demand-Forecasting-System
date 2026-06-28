"""
profit_router.py — Profit summary and selling price management
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from src.database import get_db
from src.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Profit"])


class SellingPriceUpdate(BaseModel):
    selling_price: float


@router.get("/profit-summary")
def profit_summary(db=Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    """
    Per-SKU profit summary for the last 30 days.
    Only includes items where selling_price > 0.
    """
    rows = db.execute("""
        SELECT
            i.sku,
            i.product_name,
            i.selling_price,
            i.cost_per_unit,
            COALESCE(SUM(s.quantity), 0) AS units_sold,
            ROUND(COALESCE(SUM(s.quantity), 0) * i.selling_price, 2) AS gross_revenue,
            ROUND(COALESCE(SUM(s.quantity), 0) * i.cost_per_unit, 2) AS cogs,
            ROUND(COALESCE(SUM(s.quantity), 0) * (i.selling_price - i.cost_per_unit), 2) AS gross_profit
        FROM inventory_items i
        LEFT JOIN daily_sales s
            ON i.sku = s.sku AND s.sale_date >= date('now', '-30 days')
        WHERE i.selling_price > 0
        GROUP BY i.sku
        ORDER BY gross_profit DESC
    """).fetchall()

    by_sku = []
    total_revenue = 0.0
    total_cogs = 0.0
    total_profit = 0.0

    for r in rows:
        d = dict(r)
        rev = d["gross_revenue"] or 0
        profit = d["gross_profit"] or 0
        d["margin_pct"] = round((profit / rev * 100) if rev > 0 else 0, 1)
        by_sku.append(d)
        total_revenue += rev
        total_cogs += (d["cogs"] or 0)
        total_profit += profit

    return {
        "total_revenue": round(total_revenue, 2),
        "total_cogs": round(total_cogs, 2),
        "total_profit": round(total_profit, 2),
        "margin_pct": round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
        "by_sku": by_sku,
        "has_selling_prices": len(by_sku) > 0,
    }


@router.put("/inventory/{sku}/selling-price")
def update_selling_price(sku: str, body: SellingPriceUpdate, db=Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    sku = sku.strip().upper()
    item = db.execute("SELECT sku FROM inventory_items WHERE sku = ?", (sku,)).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' not found.")
    if body.selling_price < 0:
        raise HTTPException(status_code=400, detail="Selling price cannot be negative.")

    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE inventory_items SET selling_price = ?, updated_at = ? WHERE sku = ?",
        (body.selling_price, now, sku),
    )
    db.commit()
    return {"sku": sku, "selling_price": body.selling_price}
