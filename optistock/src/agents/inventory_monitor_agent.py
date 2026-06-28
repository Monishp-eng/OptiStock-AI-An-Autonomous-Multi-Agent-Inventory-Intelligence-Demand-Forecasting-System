# src/agents/inventory_monitor_agent.py
"""
OptiStock Inventory Monitoring Agent
Proactively scans inventory levels, calculates days of supply, and triggers low-stock events.
"""

import logging
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("agent.inventory_monitor")


class InventoryMonitorAgent(BaseAgent):
    """
    Scans all SKUs, calculates stock status based on demand and reorder points,
    and publishes alerts when stock levels drop below thresholds.
    """

    def __init__(self):
        super().__init__(
            agent_name="inventory_monitor",
            description="Monitors stock levels, calculates days of supply, and alerts for critical/low stock",
            system_prompt=(
                "You are an expert inventory supervisor. "
                "Analyze inventory status and describe the severity of "
                "stockout risks in simple business terms."
            ),
        )

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Scan inventory items and publish alerts for items needing attention."""
        actions = []
        events = []
        errors = []
        alerts_summary = []

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

        try:
            from src.inventory_optimizer import InventoryOptimizer, StockStatus
            optimizer = InventoryOptimizer()
            actions.append("Initialized InventoryOptimizer engine for statistical audits")
        except Exception as opt_err:
            logger.warning(f"InventoryOptimizer import failed, using basic rules: {opt_err}")
            optimizer = None

        try:
            # Fetch inventory items
            items = conn.execute("""
                SELECT sku, product_name, category, current_stock,
                       cost_per_unit, supplier, defect_rate, lead_time_days
                FROM inventory_items
            """).fetchall()

            if not items:
                conn.close()
                return AgentResult(
                    agent_name=self.agent_name,
                    status="success",
                    summary="No inventory items found to scan",
                    actions_taken=["Scanned database — empty"],
                )

            actions.append(f"Fetched {len(items)} items from database")

            scanned_count = 0
            alert_count = 0

            for row in items:
                sku = row["sku"]
                product_name = row["product_name"]
                current_stock = row["current_stock"] or 0
                cost = row["cost_per_unit"] or 0.0
                lead_time = row["lead_time_days"] or 7
                supplier = row["supplier"] or "Unknown"

                # Get all daily sales for this SKU to calculate standard deviations and statistics
                sales_history = conn.execute("""
                    SELECT quantity, sale_date
                    FROM daily_sales
                    WHERE sku = ?
                    ORDER BY sale_date
                """, (sku,)).fetchall()

                daily_demands = [float(s["quantity"] or 0) for s in sales_history]
                
                # Default baseline daily sales calculation
                sales_30d = conn.execute("""
                    SELECT SUM(quantity) as total_sold
                    FROM daily_sales
                    WHERE sku = ? AND sale_date >= date('now', '-30 days')
                """, (sku,)).fetchone()
                total_sold = sales_30d["total_sold"] if sales_30d and sales_30d["total_sold"] else 0
                avg_daily_sales = total_sold / 30.0
                
                if avg_daily_sales <= 0:
                    avg_daily_sales = 0.5
                if not daily_demands:
                    daily_demands = [avg_daily_sales]

                status = "STOCK_HEALTHY"
                priority = "low"
                safety_stock = int(avg_daily_sales * lead_time * 0.2)
                reorder_point = int(avg_daily_sales * lead_time) + safety_stock
                days_of_stock = current_stock / avg_daily_sales

                if optimizer:
                    try:
                        # Call actual statistical calculation engine
                        metrics = optimizer.full_analysis(
                            sku=sku,
                            product_name=product_name,
                            current_stock=current_stock,
                            daily_demands=daily_demands,
                            lead_time_days=lead_time,
                            unit_cost=cost
                        )
                        safety_stock = metrics.safety_stock
                        reorder_point = metrics.reorder_point
                        days_of_stock = metrics.days_of_supply
                        
                        # Map StockStatus enum string values to Agent Events
                        if metrics.stock_status in (StockStatus.CRITICAL.value, StockStatus.STOCKOUT_RISK.value):
                            status = "STOCK_CRITICAL"
                            priority = "critical"
                        elif metrics.stock_status == StockStatus.LOW_STOCK.value:
                            status = "STOCK_LOW"
                            priority = "high"
                        elif metrics.stock_status == StockStatus.OVERSTOCK.value:
                            status = "STOCK_OVERSTOCK"
                            priority = "medium"
                        elif metrics.stock_status in (StockStatus.SLOW_MOVING.value, StockStatus.DEAD_STOCK.value):
                            status = "STOCK_OVERSTOCK"  # treated as overstock alert
                            priority = "medium"
                            
                    except Exception as calc_err:
                        logger.warning(f"Audit calculation failed for {sku}: {calc_err}")
                        optimizer = None  # Force fallback rules

                # Fallback rule-of-thumb calculations if optimizer failed/unavailable
                if not optimizer:
                    if current_stock == 0 or days_of_stock < lead_time:
                        status = "STOCK_CRITICAL"
                        priority = "critical"
                    elif days_of_stock < lead_time * 2:
                        status = "STOCK_LOW"
                        priority = "high"
                    elif days_of_stock > 60:
                        status = "STOCK_OVERSTOCK"
                        priority = "medium"

                # Use Gemini for reasoning context if available
                explanation = self._generate_explanation(
                    product_name, current_stock, days_of_stock, lead_time, avg_daily_sales
                )

                item_info = {
                    "sku": sku,
                    "product_name": product_name,
                    "current_stock": current_stock,
                    "days_of_stock": round(days_of_stock, 1),
                    "avg_daily_sales": round(avg_daily_sales, 2),
                    "lead_time": lead_time,
                    "status": status,
                    "explanation": explanation
                }

                # Publish events for critical/low stock
                if status in ("STOCK_CRITICAL", "STOCK_LOW", "STOCK_OVERSTOCK"):
                    alert_count += 1
                    evt = self.publish_event(status, item_info, priority=priority)
                    events.append(evt)
                    alerts_summary.append(f"{sku} ({product_name}): {status.replace('STOCK_', '')} - {explanation}")
                
                scanned_count += 1

            conn.close()

            summary = f"Scanned {scanned_count} items. Found {alert_count} items requiring attention."
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary=summary,
                details={
                    "scanned_count": scanned_count,
                    "alert_count": alert_count,
                    "alerts": alerts_summary
                },
                events_published=events,
                actions_taken=actions,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"Error in inventory scanning: {e}")
            if 'conn' in locals():
                conn.close()
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Scan cycle interrupted: {e}",
                errors=[str(e)],
            )

    def _generate_explanation(
        self, name: str, stock: int, days: float, lead_time: int, avg_sales: float
    ) -> str:
        """Generate a natural-language description using Gemini or fallback."""
        if stock == 0:
            return f"{name} is completely out of stock. Customers cannot buy it."
        
        prompt = f"""You are an inventory monitoring agent.
Product: {name}
Current Stock: {stock} units
Days of supply remaining: {days:.1f} days
Supplier Lead Time: {lead_time} days
Average Daily Sales: {avg_sales:.2f} units/day

Explain the stock situation in one simple sentence.
- If days of supply is less than lead time, warn of immediate stockout risk.
- If days of supply is less than twice the lead time, warn that stock is getting low.
- If days of supply is over 60 days, mention that capital is tied up in overstock.
- Otherwise, say stock is healthy.
Do not use technical jargon. Reply with just the explanation, no JSON, no quote marks."""

        result = self.call_gemini(prompt, as_json=False)
        if result:
            return result

        # Fallback
        if stock == 0:
            return f"{name} is completely out of stock."
        elif days < lead_time:
            return f"⚠️ {name} has only {days:.1f} days of stock, but delivery takes {lead_time} days. Stockout imminent!"
        elif days < lead_time * 2:
            return f"Stock for {name} is running low ({days:.1f} days remaining)."
        elif days > 60:
            return f"Excess stock of {name} detected ({days:.1f} days remaining)."
        else:
            return f"Stock level for {name} is healthy."
