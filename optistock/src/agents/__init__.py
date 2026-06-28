# src/agents/__init__.py
"""
OptiStock Multi-Agent System
7 specialized AI agents for autonomous inventory management.
"""

from src.agents.base_agent import BaseAgent, AgentResult, AgentEvent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.inventory_monitor_agent import InventoryMonitorAgent
from src.agents.alert_notification_agent import AlertNotificationAgent
from src.agents.auto_procurement_agent import AutoProcurementAgent
from src.agents.anomaly_detection_agent import AnomalyDetectionAgent
from src.agents.supplier_intelligence_agent import SupplierIntelligenceAgent
from src.agents.scheduled_reporting_agent import ScheduledReportingAgent
from src.agents.dynamic_pricing_agent import DynamicPricingAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "AgentEvent",
    "OrchestratorAgent",
    "InventoryMonitorAgent",
    "AlertNotificationAgent",
    "AutoProcurementAgent",
    "AnomalyDetectionAgent",
    "SupplierIntelligenceAgent",
    "ScheduledReportingAgent",
    "DynamicPricingAgent",
]
