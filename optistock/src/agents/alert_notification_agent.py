# src/agents/alert_notification_agent.py
"""
OptiStock Alert & Notification Agent
Subscribes to all agent events, aggregates and deduplicates them, and routes notifications to various channels.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentResult, AgentEvent

logger = logging.getLogger("agent.alert_notification")


class AlertNotificationAgent(BaseAgent):
    """
    Subscribes to system events, aggregates them, and sends consolidated alerts
    via Email, Whatsapp wa.me links, and in-app logs.
    """

    # In-memory notifications log for in-app viewing
    _notifications_log: List[dict] = []
    # Temporary buffer for events received since last run
    _event_buffer: List[AgentEvent] = []

    def __init__(self):
        super().__init__(
            agent_name="alert_notification",
            description="Collects, prioritizes, and routes notifications via Email, WhatsApp, and In-App alerts",
            system_prompt=(
                "You are an alert coordinator. Group and translate technical "
                "alerts into friendly, actionable daily digests for a shop owner."
            ),
        )
        
        # Subscribe to all relevant events
        self.subscribe_to("STOCK_CRITICAL", self._handle_event)
        self.subscribe_to("STOCK_LOW", self._handle_event)
        self.subscribe_to("ANOMALY_DETECTED", self._handle_event)
        self.subscribe_to("PO_CREATED", self._handle_event)
        self.subscribe_to("PRICE_RECOMMENDATION", self._handle_event)
        self.subscribe_to("SUPPLIER_RISK_HIGH", self._handle_event)
        self.subscribe_to("SUPPLIER_DECLINING", self._handle_event)

    def _handle_event(self, event: AgentEvent):
        """Callback to receive events from EventBus."""
        self._event_buffer.append(event)
        logger.info(f"🔔 Notification agent buffered event: {event.event_type} from {event.source_agent}")

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Process buffered events, route notifications, and empty the buffer."""
        actions = []
        errors = []
        sent_count = 0
        channels_used = []

        if not self._event_buffer:
            return AgentResult(
                agent_name=self.agent_name,
                status="success",
                summary="No new events to process",
                actions_taken=["Checked event buffer — empty"],
            )

        events_to_process = list(self._event_buffer)
        self._event_buffer.clear()

        # Deduplicate events by SKU + event_type to avoid flooding
        deduped_events = {}
        for evt in events_to_process:
            sku = evt.data.get("sku", "global")
            key = f"{evt.event_type}_{sku}"
            # Keep the highest priority or latest event
            deduped_events[key] = evt

        actions.append(f"Deduplicated {len(events_to_process)} events down to {len(deduped_events)}")

        critical_alerts = []
        high_alerts = []
        info_alerts = []

        for key, evt in deduped_events.items():
            formatted_alert = self._format_alert(evt)
            
            # Save to in-app log
            self._notifications_log.append(formatted_alert)
            if len(self._notifications_log) > 200:
                self._notifications_log = self._notifications_log[-200:]

            if evt.priority == "critical":
                critical_alerts.append(formatted_alert)
            elif evt.priority == "high":
                high_alerts.append(formatted_alert)
            else:
                info_alerts.append(formatted_alert)

            sent_count += 1

        # Route notifications based on severity
        # 1. Critical alerts -> Send immediate email if configured
        if critical_alerts:
            email_sent = self._send_email_digest(critical_alerts, is_critical=True)
            if email_sent:
                channels_used.append("email_immediate")
                actions.append(f"Sent immediate email alert for {len(critical_alerts)} critical issues")

        # 2. Daily digest or routine routing
        # In a real app we might batch high/info alerts, here we'll simulate routing
        if high_alerts or info_alerts:
            # Send general email summary
            email_sent = self._send_email_digest(high_alerts + info_alerts, is_critical=False)
            if email_sent:
                channels_used.append("email_digest")
                actions.append("Sent general email digest")

        # Create simulated WhatsApp links for critical alerts
        for alert in critical_alerts:
            sku = alert.get("sku", "")
            msg = alert.get("message", "Alert from OptiStock")
            # Generate a WhatsApp send link (encoded)
            import urllib.parse
            phone = os.environ.get("SMTP_RECIPIENT_PHONE") or ""
            encoded_msg = urllib.parse.quote(msg)
            wa_link = f"https://wa.me/{phone}?text={encoded_msg}" if phone else f"https://wa.me/?text={encoded_msg}"
            alert["whatsapp_link"] = wa_link
            channels_used.append("whatsapp")

        # --- Persist all alerts in SQLite ---
        try:
            from src.database import get_connection
            db_conn = get_connection()
            for key, evt in deduped_events.items():
                formatted_alert = self._format_alert(evt)
                # Ensure we write WhatsApp link if present
                for ca in critical_alerts:
                    if ca["id"] == formatted_alert["id"]:
                        formatted_alert["whatsapp_link"] = ca["whatsapp_link"]
                
                db_conn.execute("""
                    INSERT OR REPLACE INTO notifications 
                        (id, timestamp, event_type, source_agent, sku, product_name, title, message, priority, whatsapp_link)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    formatted_alert["id"],
                    formatted_alert["timestamp"],
                    formatted_alert["event_type"],
                    formatted_alert["source_agent"],
                    formatted_alert["sku"],
                    formatted_alert["product_name"],
                    formatted_alert["title"],
                    formatted_alert["message"],
                    formatted_alert["priority"],
                    formatted_alert["whatsapp_link"]
                ))
            db_conn.commit()
            db_conn.close()
            actions.append(f"Persisted {len(deduped_events)} notifications in SQLite")
        except Exception as db_err:
            logger.error(f"Database insertion of alerts failed: {db_err}")
            errors.append(f"DB insert alert failed: {db_err}")

        channels_used = list(set(channels_used))
        summary = f"Processed {sent_count} notifications across channels: {', '.join(channels_used)}"

        return AgentResult(
            agent_name=self.agent_name,
            status="success",
            summary=summary,
            details={
                "processed_count": sent_count,
                "channels": channels_used,
                "critical_count": len(critical_alerts),
                "high_count": len(high_alerts),
                "info_count": len(info_alerts),
            },
            actions_taken=actions,
            errors=errors,
        )

    def _format_alert(self, event: AgentEvent) -> dict:
        """Format event into a user-friendly alert dictionary."""
        sku = event.data.get("sku", "")
        product_name = event.data.get("product_name", "")
        
        # Friendly title/message generation
        title = event.event_type.replace("_", " ").title()
        message = event.data.get("explanation") or event.data.get("reasoning") or f"Event {event.event_type} occurred."

        if event.event_type == "STOCK_CRITICAL":
            title = "🚨 Critical Stock Warning!"
        elif event.event_type == "STOCK_LOW":
            title = "⚠️ Stock Level Low"
        elif event.event_type == "STOCK_OVERSTOCK":
            title = "📦 Overstock Detected"
        elif event.event_type == "ANOMALY_DETECTED":
            title = "🔍 Data Anomaly Detected"
        elif event.event_type == "PO_CREATED":
            title = "🛒 Purchase Order Created"
            message = f"Auto-drafted purchase order for {product_name} ({sku}) created successfully."
        elif event.event_type == "SUPPLIER_RISK_HIGH":
            title = "🤝 Supplier Risk Alert"
            message = f"Supplier {event.data.get('supplier_name')} has high risk score. Performance grade: {event.data.get('grade')}."

        return {
            "id": f"{event.event_type}_{event.timestamp.replace(':', '_')}_{sku}",
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "source_agent": event.source_agent,
            "sku": sku,
            "product_name": product_name,
            "title": title,
            "message": message,
            "priority": event.priority,
            "whatsapp_link": None
        }

    def _send_email_digest(self, alerts: List[dict], is_critical: bool = False) -> bool:
        """Send email via SMTP if credentials exist."""
        smtp_email = os.environ.get("SMTP_EMAIL")
        smtp_password = os.environ.get("SMTP_PASSWORD")
        smtp_recipient = os.environ.get("SMTP_RECIPIENT") or smtp_email

        if not (smtp_email and smtp_password):
            logger.warning("SMTP email credentials not set. Skipping email alert routing.")
            return False

        try:
            subject = "🚨 CRITICAL: OptiStock Urgent Alerts" if is_critical else "📊 OptiStock Daily Agent Digest"
            
            # Simple HTML Builder
            html = f"<h2>{subject}</h2>"
            html += "<p>Here are the latest updates from your AI Agents:</p><ul>"
            for alert in alerts:
                severity_color = "red" if alert["priority"] == "critical" else "orange" if alert["priority"] == "high" else "blue"
                html += f"""
                <li style='margin-bottom: 12px; list-style-type: none; border-left: 4px solid {severity_color}; padding-left: 8px;'>
                    <strong>{alert['title']}</strong> (SKU: {alert['sku']})<br/>
                    <small>{alert['timestamp'][:16]} | Agent: {alert['source_agent']}</small><br/>
                    {alert['message']}
                </li>
                """
            html += "</ul><br/><p>Please open your OptiStock Command Center to approve pending procurement drafts.</p>"

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
            logger.error(f"Failed to send email alert: {e}")
            return False

    @classmethod
    def get_notifications(cls, limit: int = 50) -> List[dict]:
        """Class method to retrieve notifications log directly from SQLite DB."""
        try:
            from src.database import get_connection
            db_conn = get_connection()
            rows = db_conn.execute("""
                SELECT id, timestamp, event_type, source_agent, sku, product_name, title, message, priority, whatsapp_link, is_read
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
            db_conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to load notifications from database: {e}")
            # Fallback to empty
            return []
