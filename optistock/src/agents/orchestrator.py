# src/agents/orchestrator.py
"""
OptiStock Orchestrator Agent
Master coordinator that manages and schedules all specialized agents.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.agents.base_agent import BaseAgent, AgentResult, AgentStatus, EventBus

logger = logging.getLogger("agent.orchestrator")


class OrchestratorAgent:
    """
    Master orchestrator that coordinates all specialized agents.
    
    Responsibilities:
    - Registers and manages all agent instances
    - Runs scheduled agent cycles (daily, hourly, etc.)
    - Handles inter-agent dependencies
    - Provides a unified status dashboard
    - Routes events between agents
    """

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.event_bus = EventBus()
        self.is_running = False
        self.last_cycle: Optional[dict] = None
        self.cycle_count = 0
        self._cycle_history: List[dict] = []
        logger.info("🧠 Orchestrator initialized")

    # ---- Agent registration ----------------------------------------------

    def register_agent(self, agent: BaseAgent):
        """Register an agent with the orchestrator."""
        self.agents[agent.agent_name] = agent
        logger.info(f"📋 Registered agent: {agent.agent_name} ({agent.description})")

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        return self.agents.get(name)

    def list_agents(self) -> List[dict]:
        """List all registered agents with their status."""
        return [agent.get_status() for agent in self.agents.values()]

    # ---- Agent control ---------------------------------------------------

    def enable_agent(self, name: str) -> bool:
        """Enable a specific agent."""
        agent = self.agents.get(name)
        if agent:
            agent.enable()
            return True
        return False

    def disable_agent(self, name: str) -> bool:
        """Disable a specific agent."""
        agent = self.agents.get(name)
        if agent:
            agent.disable()
            return True
        return False

    # ---- Run cycles ------------------------------------------------------

    async def run_single_agent(self, agent_name: str, context: dict = None) -> AgentResult:
        """Run a specific agent by name."""
        agent = self.agents.get(agent_name)
        if not agent:
            return AgentResult(
                agent_name=agent_name,
                status="error",
                summary=f"Agent '{agent_name}' not found",
                errors=[f"Unknown agent: {agent_name}"],
            )
        return await agent.run(context or {})

    async def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Run the core monitoring cycle (P0 agents).
        Order: Inventory Monitor → Alert Notification
        """
        self.is_running = True
        try:
            cycle_start = datetime.utcnow()
            results = {}

            # Step 1: Inventory Monitoring
            if "inventory_monitor" in self.agents:
                result = await self.agents["inventory_monitor"].run({})
                results["inventory_monitor"] = result.to_dict()

            # Step 2: Process alerts
            if "alert_notification" in self.agents:
                result = await self.agents["alert_notification"].run({})
                results["alert_notification"] = result.to_dict()

            return self._build_cycle_result("monitoring", cycle_start, results)
        finally:
            self.is_running = False

    async def run_procurement_cycle(self) -> Dict[str, Any]:
        """
        Run the procurement cycle (P0 + P1 agents).
        Order: Inventory Monitor → Anomaly Detection → Auto Procurement → Alert
        """
        self.is_running = True
        try:
            cycle_start = datetime.utcnow()
            results = {}

            # Step 1: Monitor inventory
            if "inventory_monitor" in self.agents:
                result = await self.agents["inventory_monitor"].run({})
                results["inventory_monitor"] = result.to_dict()

            # Step 2: Check for anomalies
            if "anomaly_detection" in self.agents:
                result = await self.agents["anomaly_detection"].run({})
                results["anomaly_detection"] = result.to_dict()

            # Step 3: Auto-procurement for low stock items
            if "auto_procurement" in self.agents:
                result = await self.agents["auto_procurement"].run({})
                results["auto_procurement"] = result.to_dict()

            # Step 4: Send alerts
            if "alert_notification" in self.agents:
                result = await self.agents["alert_notification"].run({})
                results["alert_notification"] = result.to_dict()

            return self._build_cycle_result("procurement", cycle_start, results)
        finally:
            self.is_running = False

    async def run_full_cycle(self) -> Dict[str, Any]:
        """
        Run the complete daily cycle with ALL agents.
        Runs agents in dependency order.
        """
        self.is_running = True
        try:
            cycle_start = datetime.utcnow()
            results = {}

            agent_order = [
                "inventory_monitor",        # 1. Check stock levels
                "anomaly_detection",         # 2. Detect anomalies in data
                "supplier_intelligence",     # 3. Evaluate suppliers
                "auto_procurement",          # 4. Create POs for low stock
                "dynamic_pricing",           # 5. Recommend price changes
                "scheduled_reporting",       # 6. Generate reports
                "alert_notification",        # 7. Send all notifications (last)
            ]

            for agent_name in agent_order:
                if agent_name in self.agents:
                    agent = self.agents[agent_name]
                    if agent.enabled:
                        try:
                            logger.info(f"▶ Running {agent_name}...")
                            result = await agent.run({})
                            results[agent_name] = result.to_dict()
                        except Exception as e:
                            logger.error(f"❌ Agent {agent_name} failed in cycle: {e}")
                            results[agent_name] = {
                                "agent_name": agent_name,
                                "status": "error",
                                "errors": [str(e)],
                            }

            return self._build_cycle_result("full", cycle_start, results)
        finally:
            self.is_running = False

    async def run_report_cycle(self, report_type: str = "daily_summary") -> Dict[str, Any]:
        """Run just the reporting cycle."""
        self.is_running = True
        try:
            cycle_start = datetime.utcnow()
            results = {}

            if "scheduled_reporting" in self.agents:
                result = await self.agents["scheduled_reporting"].run(
                    {"report_type": report_type}
                )
                results["scheduled_reporting"] = result.to_dict()

            if "alert_notification" in self.agents:
                result = await self.agents["alert_notification"].run({})
                results["alert_notification"] = result.to_dict()

            return self._build_cycle_result("report", cycle_start, results)
        finally:
            self.is_running = False

    # ---- Helpers ---------------------------------------------------------

    def _build_cycle_result(
        self, cycle_type: str, start_time: datetime, results: dict
    ) -> dict:
        """Build a structured cycle result."""
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        cycle_result = {
            "cycle_type": cycle_type,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "duration_ms": round(duration_ms, 2),
            "agents_run": len(results),
            "agents_succeeded": sum(
                1 for r in results.values() if r.get("status") == "success"
            ),
            "agents_failed": sum(
                1 for r in results.values() if r.get("status") == "error"
            ),
            "results": results,
        }

        self.cycle_count += 1
        self.last_cycle = cycle_result

        # Keep last 10 cycles
        self._cycle_history.append(cycle_result)
        if len(self._cycle_history) > 10:
            self._cycle_history = self._cycle_history[-10:]

        logger.info(
            f"🔄 Cycle '{cycle_type}' complete — "
            f"{cycle_result['agents_succeeded']}/{cycle_result['agents_run']} succeeded "
            f"in {duration_ms:.0f}ms"
        )

        return cycle_result

    def get_dashboard(self) -> dict:
        """Get complete orchestrator dashboard data."""
        return {
            "orchestrator": {
                "is_running": self.is_running,
                "cycle_count": self.cycle_count,
                "last_cycle": self.last_cycle,
                "total_agents": len(self.agents),
                "enabled_agents": sum(
                    1 for a in self.agents.values() if a.enabled
                ),
            },
            "agents": self.list_agents(),
            "recent_events": self.event_bus.get_recent_events(limit=30),
            "cycle_history": list(reversed(self._cycle_history)),
        }


# ---------------------------------------------------------------------------
# Global orchestrator instance + agent factory
# ---------------------------------------------------------------------------

_orchestrator: Optional[OrchestratorAgent] = None


def get_orchestrator() -> OrchestratorAgent:
    """Get or create the global orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OrchestratorAgent()
        _register_all_agents(_orchestrator)
    return _orchestrator


def _register_all_agents(orch: OrchestratorAgent):
    """Instantiate and register all agents with the orchestrator."""
    try:
        from src.agents.inventory_monitor_agent import InventoryMonitorAgent
        orch.register_agent(InventoryMonitorAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register InventoryMonitorAgent: {e}")

    try:
        from src.agents.alert_notification_agent import AlertNotificationAgent
        orch.register_agent(AlertNotificationAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register AlertNotificationAgent: {e}")

    try:
        from src.agents.auto_procurement_agent import AutoProcurementAgent
        orch.register_agent(AutoProcurementAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register AutoProcurementAgent: {e}")

    try:
        from src.agents.anomaly_detection_agent import AnomalyDetectionAgent
        orch.register_agent(AnomalyDetectionAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register AnomalyDetectionAgent: {e}")

    try:
        from src.agents.supplier_intelligence_agent import SupplierIntelligenceAgent
        orch.register_agent(SupplierIntelligenceAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register SupplierIntelligenceAgent: {e}")

    try:
        from src.agents.scheduled_reporting_agent import ScheduledReportingAgent
        orch.register_agent(ScheduledReportingAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register ScheduledReportingAgent: {e}")

    try:
        from src.agents.dynamic_pricing_agent import DynamicPricingAgent
        orch.register_agent(DynamicPricingAgent())
    except Exception as e:
        logger.warning(f"⚠️ Could not register DynamicPricingAgent: {e}")

    logger.info(
        f"✅ Orchestrator ready with {len(orch.agents)} agents: "
        f"{', '.join(orch.agents.keys())}"
    )
