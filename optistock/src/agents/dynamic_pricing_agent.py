# src/agents/dynamic_pricing_agent.py
"""
OptiStock Dynamic Pricing Agent
Analyzes sales velocity and stock levels to recommend price optimizations.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("agent.dynamic_pricing")


class DynamicPricingAgent(BaseAgent):
    """
    Evaluates pricing opportunities for each SKU.
    Recommends markdowns for overstocks and premiums for stockout-prone items.
    """

    def __init__(self):
        super().__init__(
            agent_name="dynamic_pricing",
            description="Recommends price optimizations (discounts for overstock, markups for low-stock items)",
            system_prompt=(
                "You are a retail pricing analyst. Propose price optimizations "
                "with clear business rationale in simple shopkeeper terms."
            ),
        )

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Scan SKUs, check stock status, and propose price updates."""
        actions = []
        events = []
        errors = []
        recommendations = []

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
            items = conn.execute("""
                SELECT sku, product_name, current_stock, cost_per_unit,
                       selling_price, lead_time_days
                FROM inventory_items
            """).fetchall()

            actions.append(f"Analyzing pricing for {len(items)} products")

            for item in items:
                sku = item["sku"]
                product_name = item["product_name"]
                current_stock = item["current_stock"] or 0
                cost = item["cost_per_unit"] or 0.0
                current_price = item["selling_price"] or 0.0
                lead_time = item["lead_time_days"] or 7

                if current_price <= 0:
                    # If selling price is not set, set default to cost + 30% margin
                    current_price = round(cost * 1.30, 2)

                # Get sales velocity
                sales = conn.execute("""
                    SELECT SUM(quantity) as total_sold
                    FROM daily_sales
                    WHERE sku = ? AND sale_date >= date('now', '-30 days')
                """, (sku,)).fetchone()

                total_sold = sales["total_sold"] if sales and sales["total_sold"] else 0
                avg_daily_sales = total_sold / 30.0
                
                days_of_stock = current_stock / avg_daily_sales if avg_daily_sales > 0 else 999.0

                suggested_price = current_price
                change_type = "hold"
                change_pct = 0.0
                rationale = ""

                # 1. Overstock pricing rule (Days of supply > 60 days) -> Discount to clear
                if days_of_stock > 60 and current_stock > 10:
                    discount_rate = 0.10  # 10% discount
                    if days_of_stock > 90:
                        discount_rate = 0.15  # 15% discount for dead stock
                    
                    suggested_price = current_price * (1.0 - discount_rate)
                    # Don't price below cost
                    suggested_price = max(cost * 1.05, suggested_price)
                    suggested_price = round(suggested_price, 2)
                    
                    change_pct = -round((current_price - suggested_price) / current_price * 100, 1)
                    change_type = "discount"
                    
                # 2. Low stock / stockout pricing rule (Days of supply < lead_time) -> Increase price to slow sales
                elif days_of_stock < lead_time and current_stock > 0 and avg_daily_sales > 0:
                    markup_rate = 0.08  # 8% price increase
                    suggested_price = round(current_price * (1.0 + markup_rate), 2)
                    change_pct = round((suggested_price - current_price) / current_price * 100, 1)
                    change_type = "premium"

                # If no rule triggered, keep price the same
                if change_type == "hold":
                    rationale = f"Stock level for {product_name} is stable ({days_of_stock:.0f} days). Maintain selling price of ₹{current_price}."
                else:
                    # Use Gemini for pricing rationale
                    rationale = self._generate_rationale(
                        product_name, current_price, suggested_price, change_pct, change_type, days_of_stock
                    )

                rec = {
                    "sku": sku,
                    "product_name": product_name,
                    "current_stock": current_stock,
                    "cost": cost,
                    "current_price": current_price,
                    "suggested_price": suggested_price,
                    "change_type": change_type,
                    "change_pct": change_pct,
                    "rationale": rationale
                }
                recommendations.append(rec)
                
                # Publish event for recommended changes
                if change_type != "hold":
                    evt = self.publish_event("PRICE_RECOMMENDATION", rec, priority="medium")
                    events.append(evt)
                    actions.append(f"Recommended {change_type} for {sku}: ₹{current_price} -> ₹{suggested_price}")

            conn.close()

            summary = f"Scanned {len(items)} items. Recommended {len(events)} price modifications."
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary=summary,
                details={"recommendations": recommendations},
                events_published=events,
                actions_taken=actions,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"Pricing engine error: {e}")
            if 'conn' in locals():
                conn.close()
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Pricing run failed: {e}",
                errors=[str(e)],
            )

    def _generate_rationale(
        self, name: str, old: float, new: float, pct: float, change_type: str, days: float
    ) -> str:
        """Call Gemini to get pricing rationale, or return fallback."""
        prompt = f"""You are a dynamic pricing advisor for an Indian store owner.
Product: {name}
Current Price: ₹{old}
Suggested Price: ₹{new} (Change of {pct:+.1f}%)
Stock Status: {change_type} situation with {days:.1f} days of supply.

Provide a 1-sentence explanation of why the shopkeeper should change the price.
- If it's a discount, mention freeing up cash from slow stock.
- If it's a premium, mention slowing down sales velocity to prevent running out before new stock arrives.
Do not use technical economics terms. Reply with just the sentence, no quotes."""

        result = self.call_gemini(prompt, as_json=False)
        if result:
            return result

        # Fallback
        if change_type == "discount":
            return f"Suggesting a {abs(pct):.1f}% discount to speed up sales of {name} and recover cash from slow stock."
        else:
            return f"Suggesting a temporary {pct:.1f}% markup to slow sales velocity and avoid running out of {name} before restocking."
