# src/agents/supplier_intelligence_agent.py
"""
OptiStock Supplier Intelligence Agent
Continuously evaluates supplier performance and recommends alternatives.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("agent.supplier_intelligence")


class SupplierIntelligenceAgent(BaseAgent):
    """
    Evaluates all suppliers using multi-dimensional scoring,
    tracks performance trends, and flags declining suppliers.
    """

    # Store previous scores to detect trends
    _previous_scores: Dict[str, float] = {}

    def __init__(self):
        super().__init__(
            agent_name="supplier_intelligence",
            description="Evaluates supplier reliability, quality, and pricing — flags declining suppliers",
            system_prompt=(
                "You are a supplier evaluation expert for an MSME. "
                "Analyze supplier performance data and provide actionable "
                "recommendations in simple business language."
            ),
        )

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Evaluate all suppliers and generate scorecards."""
        actions = []
        events = []
        errors = []
        scorecards = []

        try:
            from src.database import get_db
            db = get_db()
        except Exception as e:
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Database unavailable: {e}",
                errors=[str(e)],
            )

        # Fetch suppliers
        try:
            suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        except Exception:
            suppliers = []

        if not suppliers:
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary="No suppliers found in database",
                actions_taken=["Checked suppliers table — empty"],
            )

        # Fetch order history for delivery scoring
        try:
            orders = db.execute("""
                SELECT supplier_id, status, quantity,
                       ordered_at, expected_delivery_at
                FROM purchase_orders
                WHERE supplier_id IS NOT NULL
            """).fetchall()
            order_map: Dict[int, list] = {}
            for o in orders:
                sid = o["supplier_id"]
                if sid not in order_map:
                    order_map[sid] = []
                order_map[sid].append(dict(o))
        except Exception:
            order_map = {}

        # Fetch inventory items for defect/lead-time data
        try:
            items = db.execute("""
                SELECT supplier, defect_rate, lead_time_days, cost_per_unit
                FROM inventory_items
            """).fetchall()
            supplier_items: Dict[str, list] = {}
            for item in items:
                name = item["supplier"] or ""
                if name not in supplier_items:
                    supplier_items[name] = []
                supplier_items[name].append(dict(item))
        except Exception:
            supplier_items = {}

        for supplier in suppliers:
            s = dict(supplier)
            sid = s.get("id")
            sname = s.get("name", "Unknown")

            # --- Calculate multi-dimensional score ---
            scores = {}

            # 1. Delivery reliability (35%)
            s_orders = order_map.get(sid, [])
            if s_orders:
                delivered = sum(1 for o in s_orders if o["status"] == "delivered")
                total = len(s_orders)
                delivery_rate = delivered / total if total > 0 else 0.5
            else:
                delivery_rate = 0.5  # neutral if no data
            scores["delivery"] = round(delivery_rate * 100, 1)

            # 2. Quality (30%) — from defect rates
            s_items = supplier_items.get(sname, [])
            if s_items:
                avg_defect = sum(i.get("defect_rate", 0.05) for i in s_items) / len(s_items)
                quality_score = max(0, (1 - avg_defect * 10)) * 100
            else:
                quality_score = 70  # neutral
            scores["quality"] = round(quality_score, 1)

            # 3. Price competitiveness (20%)
            if s_items:
                avg_cost = sum(i.get("cost_per_unit", 0) for i in s_items) / len(s_items)
                # Lower cost = higher score (normalized heuristic)
                price_score = max(0, min(100, 100 - (avg_cost / 50) * 10))
            else:
                price_score = 60
            scores["price"] = round(price_score, 1)

            # 4. Responsiveness (15%) — estimated from lead times
            if s_items:
                avg_lead = sum(i.get("lead_time_days", 7) for i in s_items) / len(s_items)
                responsiveness = max(0, min(100, 100 - (avg_lead - 3) * 5))
            else:
                responsiveness = 60
            scores["responsiveness"] = round(responsiveness, 1)

            # Weighted total
            total_score = (
                scores["delivery"] * 0.35
                + scores["quality"] * 0.30
                + scores["price"] * 0.20
                + scores["responsiveness"] * 0.15
            )
            total_score = round(total_score, 1)

            # Grade
            if total_score >= 90:
                grade = "A"
            elif total_score >= 75:
                grade = "B"
            elif total_score >= 60:
                grade = "C"
            elif total_score >= 45:
                grade = "D"
            else:
                grade = "F"

            # Trend detection
            prev = self._previous_scores.get(sname)
            trend = "stable"
            if prev is not None:
                diff = total_score - prev
                if diff > 5:
                    trend = "improving"
                elif diff < -5:
                    trend = "declining"

            self._previous_scores[sname] = total_score

            # Generate AI review or fallback
            review = self._generate_review(
                sname, scores, total_score, grade, trend, len(s_orders)
            )

            scorecard = {
                "supplier_id": sid,
                "supplier_name": sname,
                "scores": scores,
                "total_score": total_score,
                "grade": grade,
                "trend": trend,
                "order_count": len(s_orders),
                "review": review,
            }
            scorecards.append(scorecard)
            actions.append(f"Scored {sname}: {grade} ({total_score})")

            # Publish events for concerning suppliers
            if total_score < 50 or grade in ("D", "F"):
                evt = self.publish_event("SUPPLIER_RISK_HIGH", {
                    "supplier_name": sname,
                    "grade": grade,
                    "total_score": total_score,
                    "trend": trend,
                }, priority="high")
                events.append(evt)

            if trend == "declining":
                evt = self.publish_event("SUPPLIER_DECLINING", {
                    "supplier_name": sname,
                    "previous_score": prev,
                    "current_score": total_score,
                }, priority="medium")
                events.append(evt)

            # Always publish score update
            self.publish_event("SUPPLIER_SCORE_UPDATED", {
                "supplier_name": sname,
                "total_score": total_score,
                "grade": grade,
            }, priority="low")

        # AI summary of all suppliers
        summary = self._build_summary(scorecards)

        return AgentResult(
            agent_name=self.agent_name,
            status="success",
            summary=summary,
            details={
                "scorecards": scorecards,
                "total_suppliers": len(scorecards),
                "high_risk": sum(1 for s in scorecards if s["grade"] in ("D", "F")),
                "declining": sum(1 for s in scorecards if s["trend"] == "declining"),
            },
            events_published=events,
            actions_taken=actions,
            errors=errors,
        )

    def _generate_review(
        self, name: str, scores: dict, total: float,
        grade: str, trend: str, order_count: int
    ) -> str:
        """Generate a performance review using Gemini or fallback."""
        prompt = f"""You are evaluating a supplier for a small Indian business.
Supplier: {name}
Scores: Delivery={scores['delivery']}%, Quality={scores['quality']}%, 
        Price={scores['price']}%, Responsiveness={scores['responsiveness']}%
Overall: {total}/100 (Grade {grade}), Trend: {trend}
Order history: {order_count} orders

Write a 2-3 sentence performance review in simple language.
If grade is D or F, recommend finding alternatives.
If trend is declining, warn the business owner.
Reply with just the review text, no JSON."""

        result = self.call_gemini(prompt, as_json=False)
        if result:
            return result

        # Fallback
        if grade in ("A", "B"):
            return f"{name} is performing well with a {grade} grade ({total}/100). Keep this supplier relationship strong."
        elif grade == "C":
            msg = f"{name} is average (Grade {grade}, {total}/100)."
            if trend == "declining":
                msg += " Their performance has been declining — monitor closely."
            return msg
        else:
            return (
                f"⚠️ {name} has a poor rating (Grade {grade}, {total}/100). "
                f"Consider finding alternative suppliers to reduce risk."
            )

    def _build_summary(self, scorecards: list) -> str:
        """Build an overall summary of supplier evaluations."""
        total = len(scorecards)
        high_risk = sum(1 for s in scorecards if s["grade"] in ("D", "F"))
        declining = sum(1 for s in scorecards if s["trend"] == "declining")
        top = sorted(scorecards, key=lambda x: x["total_score"], reverse=True)

        summary = f"Evaluated {total} suppliers. "
        if high_risk:
            summary += f"⚠️ {high_risk} high-risk supplier(s). "
        if declining:
            summary += f"📉 {declining} declining. "
        if top:
            summary += f"Best: {top[0]['supplier_name']} ({top[0]['grade']})."
        return summary
