# src/agents/auto_procurement_agent.py
"""
OptiStock Auto-Procurement Agent
Listens for low-stock warnings, calculates economic order quantities, identifies suppliers,
drafts negotiation emails, and logs pending purchase orders.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult, AgentEvent

logger = logging.getLogger("agent.auto_procurement")


class AutoProcurementAgent(BaseAgent):
    """
    Automates purchase order drafts. When stock is low, it runs forecasts,
    calculates EOQ, identifies the supplier, drafts an email, and logs a PO.
    """

    # Buffer for low stock events received
    _low_stock_skus: List[str] = []

    def __init__(self, auto_approve_threshold: float = 10000.0):
        super().__init__(
            agent_name="auto_procurement",
            description="Auto-drafts purchase orders and negotiation emails for low-stock items",
            system_prompt=(
                "You are an automated procurement bot. Draft detailed purchase orders "
                "and professional supplier procurement emails in simple business terms."
            ),
        )
        self.auto_approve_threshold = auto_approve_threshold
        
        # Subscribe to low stock events
        self.subscribe_to("STOCK_CRITICAL", self._handle_low_stock)
        self.subscribe_to("STOCK_LOW", self._handle_low_stock)

    def _handle_low_stock(self, event: AgentEvent):
        sku = event.data.get("sku")
        if sku and sku not in self._low_stock_skus:
            self._low_stock_skus.append(sku)

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Scan low stock SKUs, calculate optimal quantities, and create POs."""
        actions = []
        events = []
        errors = []
        orders_created = []

        try:
            from src.database import get_connection
            conn = get_connection()
        except Exception as e:
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Database connection failed: {e}",
                errors=[str(e)],
            )

        # Work on buffered SKUs, or scan all low-stock items from DB if buffer is empty (for manual runs)
        skus_to_process = list(self._low_stock_skus)
        self._low_stock_skus.clear()

        if not skus_to_process:
            # Fallback: scan database directly for items below reorder points
            try:
                # Simple rule: current_stock < lead_time_days * avg_daily_sales (under 2x lead time demand)
                low_stock_rows = conn.execute("""
                    SELECT sku FROM inventory_items 
                    WHERE current_stock <= (lead_time_days * 2)
                """).fetchall()
                skus_to_process = [row["sku"] for row in low_stock_rows]
                actions.append(f"Scanned DB and found {len(skus_to_process)} low-stock items")
            except Exception as e:
                conn.close()
                return AgentResult(
                    agent_name=self.agent_name,
                    status="error",
                    summary=f"Direct scan failed: {e}",
                    errors=[str(e)],
                )

        if not skus_to_process:
            conn.close()
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary="No low-stock items found to procure",
                actions_taken=["Checked buffer and direct DB scan — 0 low-stock items"],
            )

        # Load helper forecasting and optimization modules
        try:
            from src.advanced_forecasting import run_hybrid_forecast
            forecasting_available = True
        except ImportError:
            forecasting_available = False

        try:
            from src.inventory_optimizer import InventoryOptimizer
            optimizer = InventoryOptimizer()
        except ImportError:
            optimizer = None

        for sku in skus_to_process:
            # 1. Fetch item details
            item = conn.execute("""
                SELECT sku, product_name, current_stock, cost_per_unit, 
                       supplier, defect_rate, lead_time_days
                FROM inventory_items WHERE sku = ?
            """, (sku,)).fetchone()

            if not item:
                continue

            product_name = item["product_name"]
            current_stock = item["current_stock"] or 0
            unit_cost = item["cost_per_unit"] or 0
            lead_time = item["lead_time_days"] or 7
            supplier_name = item["supplier"] or "Unknown"

            # 2. Get sales history
            sales_rows = conn.execute("""
                SELECT quantity, sale_date FROM daily_sales 
                WHERE sku = ? ORDER BY sale_date
            """, (sku,)).fetchall()
            
            daily_demands = [row["quantity"] for row in sales_rows]
            avg_daily = sum(daily_demands) / len(daily_demands) if daily_demands else 1.0

            # 3. Forecast 30-day demand
            forecast_30 = int(avg_daily * 30)
            if forecasting_available and len(daily_demands) >= 7:
                try:
                    import pandas as pd
                    sales_df = pd.DataFrame([{"ds": r["sale_date"], "y": r["quantity"]} for r in sales_rows])
                    sales_df['ds'] = pd.to_datetime(sales_df['ds'])
                    fc_res = run_hybrid_forecast(sales_df, sku, forecast_days=30)
                    if fc_res.get("success"):
                        forecast_30 = int(fc_res.get("forecasted_demand_30_days", forecast_30))
                except Exception as e:
                    logger.warning(f"Prophet forecast failed for {sku}: {e}")

            # 4. Calculate optimal order quantity (EOQ)
            order_qty = max(10, int(forecast_30 * 1.5))  # Default baseline fallback
            if optimizer:
                try:
                    # Let's calculate eoq
                    eoq_val, _ = optimizer.calculate_eoq(
                        annual_demand=avg_daily * 365,
                        unit_cost=unit_cost
                    )
                    order_qty = max(1, eoq_val)
                except Exception as e:
                    logger.warning(f"EOQ optimization failed for {sku}: {e}")

            # 5. Fetch supplier ID from DB
            supplier_row = conn.execute(
                "SELECT id, email, whatsapp_number FROM suppliers WHERE name = ?", (supplier_name,)
            ).fetchone()
            supplier_id = supplier_row["id"] if supplier_row else None
            supplier_email = supplier_row["email"] if supplier_row else None

            # 6. Calculate cost and approval status
            total_cost = order_qty * unit_cost
            status = "pending"
            notes = f"Auto-drafted by Auto-Procurement Agent. Value: ₹{total_cost:,.2f}."
            if total_cost < self.auto_approve_threshold:
                notes += " Below approval threshold — recommended for auto-approval."

            # 7. Draft supplier email
            email_subject, email_body = self._draft_procurement_email(
                product_name, supplier_name, order_qty, notes
            )

            # 8. Record in DB
            now = datetime.utcnow().isoformat()
            expected_delivery = (datetime.utcnow() + timedelta(days=lead_time)).isoformat()[:10]

            try:
                cur = conn.execute("""
                    INSERT INTO purchase_orders
                        (sku, supplier_id, quantity, status, unit_cost, total_cost,
                         ordered_at, expected_delivery_at, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sku, supplier_id, order_qty, status, unit_cost, total_cost, now, expected_delivery, notes))
                
                po_id = cur.lastrowid
                conn.commit()

                order_info = {
                    "po_id": po_id,
                    "sku": sku,
                    "product_name": product_name,
                    "supplier_name": supplier_name,
                    "supplier_id": supplier_id,
                    "supplier_email": supplier_email,
                    "quantity": order_qty,
                    "unit_cost": unit_cost,
                    "total_cost": total_cost,
                    "expected_delivery_at": expected_delivery,
                    "email_draft": {
                        "subject": email_subject,
                        "body": email_body
                    }
                }

                orders_created.append(order_info)
                actions.append(f"Created PO #{po_id} for {product_name} (Qty: {order_qty}, Cost: ₹{total_cost:,.2f})")

                # Publish PO_CREATED event
                evt = self.publish_event("PO_CREATED", order_info, priority="high")
                events.append(evt)

            except Exception as e:
                logger.error(f"Failed to insert PO for {sku}: {e}")
                errors.append(f"Failed to record PO for {sku}: {e}")

        conn.close()

        summary = f"Created {len(orders_created)} purchase order drafts."
        return AgentResult(
            agent_name=self.agent_name,
            status="success",
            summary=summary,
            details={"orders": orders_created},
            events_published=events,
            actions_taken=actions,
            errors=errors,
        )

    def _draft_procurement_email(
        self, name: str, supplier: str, qty: int, notes: str
    ) -> tuple:
        """Draft a supplier negotiation email using Gemini or fallback."""
        prompt = f"""You are a purchase officer drafting a procurement order.
Product: {name}
Supplier: {supplier}
Quantity: {qty} units
Notes: {notes}

Write a professional email subject and body requesting a quote and delivery timeline.
Format your response exactly as:
Subject: [Subject Line]
---
[Email Body]

Do not include any extra introductory text. Just subject, separator, and body."""

        result = self.call_gemini(prompt, as_json=False)
        if result and "---" in result:
            parts = result.split("---")
            subj = parts[0].replace("Subject:", "").strip()
            body = parts[1].strip()
            return subj, body

        # Fallback
        subj = f"Procurement Order Request - {name}"
        body = f"""Dear {supplier} Team,

We would like to place an order for {qty} units of '{name}'. 

Please share the pricing, bulk discounts, and expected delivery timeline for this quantity.

Thank you,
OptiStock Procurement Team"""
        return subj, body
