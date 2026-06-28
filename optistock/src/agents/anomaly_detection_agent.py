# src/agents/anomaly_detection_agent.py
"""
OptiStock Anomaly Detection Agent
Analyzes historical sales data, supplier pricing, and stock levels to detect outliers and suspicious deviations.
"""

import logging
import numpy as np
from datetime import datetime
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("agent.anomaly_detection")


class AnomalyDetectionAgent(BaseAgent):
    """
    Scans sales transactions, supplier cost rates, and stock records.
    Uses IQR and standard deviations to detect anomalies, then contextualizes them with Gemini.
    """

    def __init__(self):
        super().__init__(
            agent_name="anomaly_detection",
            description="Analyzes transaction logs and pricing to flag suspicious cost changes or demand shocks",
            system_prompt=(
                "You are a retail data auditor. Analyze transaction anomalies "
                "and explain their likely business causes in simple, everyday language."
            ),
        )

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Scan SQLite database for anomalies in sales volume and supplier unit costs."""
        actions = []
        events = []
        errors = []
        anomalies_found = []

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
            # 1. Check for sales demand anomalies per SKU
            # We look at sales in the last 30 days
            skus_rows = conn.execute("SELECT sku, product_name FROM inventory_items").fetchall()
            actions.append(f"Analyzing sales history for {len(skus_rows)} products")

            for item in skus_rows:
                sku = item["sku"]
                product_name = item["product_name"]

                sales_history = conn.execute("""
                    SELECT quantity, sale_date FROM daily_sales
                    WHERE sku = ? AND sale_date >= date('now', '-45 days')
                    ORDER BY sale_date
                """, (sku,)).fetchall()

                if len(sales_history) < 5:
                    # Not enough historical data to establish baseline
                    continue

                quantities = np.array([r["quantity"] for r in sales_history])
                dates = [r["sale_date"] for r in sales_history]

                # Statistical thresholds using IQR
                q1 = np.percentile(quantities, 25)
                q3 = np.percentile(quantities, 75)
                iqr = q3 - q1
                upper_bound = q3 + 1.5 * iqr
                lower_bound = max(0, q1 - 1.5 * iqr)

                mean_val = np.mean(quantities)
                std_val = np.std(quantities)

                # Look for anomalies in the most recent 7 days of sales
                for i in range(len(sales_history) - 7, len(sales_history)):
                    if i < 0:
                        continue
                    
                    qty = quantities[i]
                    date = dates[i]

                    is_anomaly = False
                    reason = ""
                    severity = "medium"

                    # Check for spikes
                    if qty > upper_bound and qty > mean_val + 2 * std_val and qty > 5:
                        is_anomaly = True
                        reason = f"Sales spike: Sold {qty} units, average is {mean_val:.1f} units"
                        severity = "high" if qty > mean_val + 4 * std_val else "medium"
                    
                    # Check for crashes (only if average is high enough to drop)
                    elif qty < lower_bound and mean_val > 10 and qty < mean_val * 0.1:
                        is_anomaly = True
                        reason = f"Sales crash: Sold {qty} units, average is {mean_val:.1f} units"
                        severity = "medium"

                    if is_anomaly:
                        explanation = self._explain_anomaly(
                            product_name, qty, mean_val, date, reason
                        )

                        anomaly = {
                            "sku": sku,
                            "product_name": product_name,
                            "type": "sales_anomaly",
                            "date": date,
                            "value": int(qty),
                            "historical_average": round(float(mean_val), 1),
                            "deviation_reason": reason,
                            "severity": severity,
                            "explanation": explanation
                        }
                        anomalies_found.append(anomaly)

                        # Publish event
                        evt = self.publish_event("ANOMALY_DETECTED", anomaly, priority=severity)
                        events.append(evt)

            # 2. Check for supplier cost anomalies
            # Look at purchase orders for price variations
            cost_anomalies = conn.execute("""
                SELECT o.id, o.sku, i.product_name, o.unit_cost, o.ordered_at, s.name as supplier_name,
                       (SELECT AVG(unit_cost) FROM purchase_orders WHERE sku = o.sku AND id != o.id) as avg_cost
                FROM purchase_orders o
                JOIN inventory_items i ON o.sku = i.sku
                LEFT JOIN suppliers s ON o.supplier_id = s.id
                WHERE o.ordered_at >= date('now', '-30 days')
            """).fetchall()

            for order in cost_anomalies:
                po_id = order["id"]
                sku = order["sku"]
                p_name = order["product_name"]
                unit_cost = order["unit_cost"]
                avg_historical_cost = order["avg_cost"]
                supplier = order["supplier_name"] or "Unknown Supplier"

                if avg_historical_cost and avg_historical_cost > 0:
                    deviation = (unit_cost - avg_historical_cost) / avg_historical_cost
                    if deviation > 0.30:  # > 30% increase
                        reason = f"Supplier cost spike: Charged ₹{unit_cost:.2f} (avg is ₹{avg_historical_cost:.2f})"
                        
                        prompt = f"""Supplier {supplier} charged ₹{unit_cost:.2f} for {p_name} ({sku}), which is historically ₹{avg_historical_cost:.2f}.
Explain this cost spike in one simple sentence and suggest looking for other suppliers."""
                        
                        explanation = self.call_gemini(prompt, as_json=False) or f"Supplier price for {p_name} is 30%+ higher than normal."

                        anomaly = {
                            "sku": sku,
                            "product_name": p_name,
                            "type": "cost_anomaly",
                            "po_id": po_id,
                            "value": float(unit_cost),
                            "historical_average": round(float(avg_historical_cost), 2),
                            "deviation_reason": reason,
                            "severity": "high",
                            "explanation": explanation
                        }
                        anomalies_found.append(anomaly)
                        
                        evt = self.publish_event("ANOMALY_DETECTED", anomaly, priority="high")
                        events.append(evt)

            conn.close()

            summary = f"Scanned data. Detected {len(anomalies_found)} anomalies."
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary=summary,
                details={"anomalies": anomalies_found, "count": len(anomalies_found)},
                events_published=events,
                actions_taken=actions,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"Error in anomaly detection run: {e}")
            if 'conn' in locals():
                conn.close()
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Audit failed: {e}",
                errors=[str(e)],
            )

    def _explain_anomaly(
        self, name: str, qty: int, avg: float, date: str, reason: str
    ) -> str:
        """Use Gemini to explain/contextualize a sales anomaly, or return fallback."""
        prompt = f"""You are a business consultant.
Product: {name}
Anomaly Date: {date}
Sales quantity today: {qty}
Historical average daily sales: {avg:.1f}
Reason flag: {reason}

Explain why this anomaly might have happened in one simple, realistic sentence. 
(For example: a holiday weekend, a bulk buyer, weather changes, or supply issues).
Do not use technical statistical language. Reply with just the explanation, no quote marks."""

        result = self.call_gemini(prompt, as_json=False)
        if result:
            return result

        # Fallback
        if qty > avg:
            return f"Significant sales surge for {name} on {date}. Could be a promotional effect or bulk buyer."
        else:
            return f"Sudden drop in sales volume for {name} on {date}. Check if product was out-of-stock."
