# src/agents/scheduled_reporting_agent.py
"""
OptiStock Scheduled Reporting Agent
Generates structured daily, weekly, and monthly reports detailing inventory health, pricing suggestions, and alerts.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("agent.scheduled_reporting")


class ScheduledReportingAgent(BaseAgent):
    """
    Assembles summaries of inventory levels, supplier scores, and sales performance.
    Uses Gemini to write a high-level executive narrative.
    """

    def __init__(self):
        super().__init__(
            agent_name="scheduled_reporting",
            description="Generates daily inventory summaries, weekly performance reviews, and monthly profit reports",
            system_prompt=(
                "You are an executive business writer. Draft concise executive Summaries "
                "summarizing stock status, revenue, and concerns for business owners."
            ),
        )

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Generate a report based on the request context type."""
        report_type = context.get("report_type", "daily_summary")
        actions = []
        errors = []

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
            # 1. Fetch system statistics
            total_skus = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
            total_stock = conn.execute("SELECT SUM(current_stock) FROM inventory_items").fetchone()[0] or 0
            total_value = conn.execute("SELECT SUM(current_stock * cost_per_unit) FROM inventory_items").fetchone()[0] or 0.0

            sales_30d = conn.execute("""
                SELECT SUM(quantity) as total_sold,
                       COUNT(DISTINCT sku) as active_skus
                FROM daily_sales
                WHERE sale_date >= date('now', '-30 days')
            """).fetchone()
            
            units_sold_30d = sales_30d["total_sold"] or 0
            active_skus_30d = sales_30d["active_skus"] or 0

            # 2. Identify top low-stock alerts
            low_stock_items = conn.execute("""
                SELECT sku, product_name, current_stock, lead_time_days
                FROM inventory_items
                WHERE current_stock <= (lead_time_days * 2)
                LIMIT 5
            """).fetchall()

            alerts_list = [
                f"{item['sku']} ({item['product_name']}): {item['current_stock']} units left"
                for item in low_stock_items
            ]

            # 3. Generate report components depending on the report_type
            report_content = {}
            if report_type == "daily_summary":
                report_content = self._generate_daily_summary(
                    total_skus, total_stock, total_value, units_sold_30d, alerts_list
                )
            elif report_type == "weekly_deep_dive":
                # Get sales trend (last 7 days vs previous 7 days)
                sales_this_week = conn.execute("""
                    SELECT SUM(quantity) FROM daily_sales
                    WHERE sale_date >= date('now', '-7 days')
                """).fetchone()[0] or 0
                
                sales_prev_week = conn.execute("""
                    SELECT SUM(quantity) FROM daily_sales
                    WHERE sale_date >= date('now', '-14 days') AND sale_date < date('now', '-7 days')
                """).fetchone()[0] or 0

                trend = "increase" if sales_this_week >= sales_prev_week else "decrease"
                pct = abs(sales_this_week - sales_prev_week) / max(1, sales_prev_week) * 100
                trend_str = f"{trend.title()} of {pct:.1f}% ({sales_this_week} vs {sales_prev_week} units)"

                report_content = self._generate_weekly_deep_dive(
                    total_skus, total_value, units_sold_30d, trend_str, alerts_list
                )
            elif report_type == "monthly_pnl":
                # Get revenue/profit estimates
                # We calculate from inventory_items selling_price if set, or mock margins
                profit_stats = conn.execute("""
                    SELECT 
                        SUM(s.quantity * i.selling_price) as gross_revenue,
                        SUM(s.quantity * i.cost_per_unit) as cogs,
                        SUM(s.quantity * (i.selling_price - i.cost_per_unit)) as gross_profit
                    FROM daily_sales s
                    JOIN inventory_items i ON s.sku = i.sku
                    WHERE s.sale_date >= date('now', '-30 days')
                """).fetchone()

                revenue = profit_stats["gross_revenue"] or 0.0
                cogs = profit_stats["cogs"] or 0.0
                profit = profit_stats["gross_profit"] or 0.0
                margin = (profit / revenue * 100) if revenue > 0 else 0.0

                report_content = self._generate_monthly_pnl(
                    total_skus, revenue, cogs, profit, margin, units_sold_30d
                )

            # 4. Generate AI summary narrative using Gemini or fallback
            narrative = self._generate_ai_narrative(report_type, report_content)
            report_content["narrative"] = narrative

            actions.append(f"Assembled report payload for type: {report_type}")

            # 5. Email Report if credentials exist
            email_sent = self._send_report_email(report_type, report_content)
            if email_sent:
                actions.append(f"Emailed report to administrator")

            # 6. Publish Event
            self.publish_event("REPORT_GENERATED", {
                "report_type": report_type,
                "summary": narrative,
                "skus_count": total_skus,
                "sales_units": units_sold_30d
            }, priority="medium")

            conn.close()

            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary=f"Report '{report_type}' generated successfully.",
                details={"report": report_content},
                actions_taken=actions,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"Error generating scheduled report: {e}")
            if 'conn' in locals():
                conn.close()
            return AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Reporting cycle failed: {e}",
                errors=[str(e)],
            )

    def _generate_daily_summary(self, skus, stock, value, sales_30d, alerts) -> dict:
        return {
            "title": "Daily Inventory Digest",
            "date": datetime.now().isoformat()[:10],
            "metrics": {
                "Total Products": skus,
                "Total Items in Stock": stock,
                "Valuation": f"₹{value:,.2f}",
                "Sales (30d)": f"{sales_30d} units"
            },
            "alerts": alerts,
        }

    def _generate_weekly_deep_dive(self, skus, value, sales_30d, trend, alerts) -> dict:
        return {
            "title": "Weekly Supply Chain Performance",
            "date": datetime.now().isoformat()[:10],
            "metrics": {
                "Active Products": skus,
                "Asset Value": f"₹{value:,.2f}",
                "Sales Volume (30d)": f"{sales_30d} units",
                "Week-over-Week Trend": trend
            },
            "alerts": alerts,
        }

    def _generate_monthly_pnl(self, skus, revenue, cogs, profit, margin, sold) -> dict:
        return {
            "title": "Monthly Profit & Loss Statement Summary",
            "date": datetime.now().isoformat()[:10],
            "metrics": {
                "Revenue": f"₹{revenue:,.2f}",
                "Cost of Goods Sold (COGS)": f"₹{cogs:,.2f}",
                "Gross Profit": f"₹{profit:,.2f}",
                "Gross Margin": f"{margin:.1f}%",
                "Units Sold": f"{sold} units"
            },
            "alerts": []
        }

    def _generate_ai_narrative(self, report_type: str, content: dict) -> str:
        """Call Gemini to create an executive summary paragraph, or return fallback."""
        metrics_str = ", ".join([f"{k}: {v}" for k, v in content["metrics"].items()])
        alerts_str = ", ".join(content["alerts"]) if content["alerts"] else "None"

        prompt = f"""You are an executive business writer.
Report: {content['title']} ({content['date']})
Metrics: {metrics_str}
Top Alerts: {alerts_str}

Summarize this status in one clean, professional paragraph (3-4 sentences max).
Highlight the performance, note the critical concerns (if any), and provide a strategic recommendation.
Reply with just the narrative paragraph, no markup."""

        result = self.call_gemini(prompt, as_json=False)
        if result:
            return result

        # Fallback
        if report_type == "daily_summary":
            return (
                f"OptiStock Daily Summary for {content['date']}: Total of {content['metrics']['Total Products']} active products "
                f"with a valuation of {content['metrics']['Valuation']}. "
                f"There are currently {len(content['alerts'])} items showing stock warnings. Action is recommended."
            )
        elif report_type == "weekly_deep_dive":
            return (
                f"Supply chain deep dive for the week of {content['date']}. Sales show a {content['metrics']['Week-over-Week Trend']}. "
                f"Restocking draft orders have been submitted for critical items to prevent stockouts."
            )
        else:
            return (
                f"P&L performance review for the last 30 days: Gross revenue was {content['metrics']['Revenue']} "
                f"with a profit of {content['metrics']['Gross Profit']} ({content['metrics']['Gross Margin']} margin). "
                f"Pricing optimizations are ready for review to boost profit margins next month."
            )

    def _send_report_email(self, report_type: str, content: dict) -> bool:
        """Send email via SMTP if credentials exist."""
        smtp_email = os.environ.get("SMTP_EMAIL")
        smtp_password = os.environ.get("SMTP_PASSWORD")
        smtp_recipient = os.environ.get("SMTP_RECIPIENT") or smtp_email

        if not (smtp_email and smtp_password):
            return False

        try:
            subject = f"📊 OptiStock Scheduled Report: {content['title']}"
            
            # Simple HTML Builder
            html = f"<h2>{content['title']}</h2>"
            html += f"<p><strong>Date:</strong> {content['date']}</p>"
            html += "<h3>Executive Summary</h3>"
            html += f"<p style='font-style: italic; font-size: 1.1em;'>{content['narrative']}</p>"
            
            html += "<h3>Key Metrics</h3><ul>"
            for k, v in content["metrics"].items():
                html += f"<li><strong>{k}:</strong> {v}</li>"
            html += "</ul>"

            if content["alerts"]:
                html += "<h3>Urgent Action Required</h3><ul>"
                for alert in content["alerts"]:
                    html += f"<li style='color: red;'>{alert}</li>"
                html += "</ul>"

            html += "<br/><p>Generated automatically by OptiStock Agent Orchestrator.</p>"

            msg = MIMEMultipart()
            msg["From"] = smtp_email
            msg["To"] = smtp_recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(html, "html"))

            # SMTP Connection
            smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))

            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, smtp_recipient, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Failed to send report email: {e}")
            return False
