# src/routers/agents_router.py
"""
OptiStock: Agent Management API Endpoints
Provides REST API for managing, monitoring, and triggering AI agents.
"""

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from src.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["AI Agents"])


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AgentToggleRequest(BaseModel):
    """Request to enable/disable an agent."""
    enabled: bool = Field(..., description="Whether the agent should be enabled")


class AgentRunRequest(BaseModel):
    """Request to trigger a specific agent."""
    context: dict = Field(default_factory=dict, description="Optional context data")


class CycleRunRequest(BaseModel):
    """Request to run an agent cycle."""
    cycle_type: str = Field(
        "monitoring",
        description="Cycle type: 'monitoring', 'procurement', 'full', 'report'"
    )
    report_type: Optional[str] = Field(
        "daily_summary",
        description="Report type (only for 'report' cycle): 'daily_summary', 'weekly_deep_dive', 'monthly_pnl'"
    )


# ---------------------------------------------------------------------------
# Helper: get orchestrator (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

def _get_orchestrator():
    """Lazy import to avoid circular dependency at module load."""
    from src.agents.orchestrator import get_orchestrator
    return get_orchestrator()


# ---------------------------------------------------------------------------
# Dashboard Endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_agent_dashboard(current_user: dict = Depends(get_current_user)):
    """
    Get the complete agent dashboard: all agents status, recent events,
    cycle history, and orchestrator state.
    """
    try:
        orch = _get_orchestrator()
        return orch.get_dashboard()
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_all_agents_status(current_user: dict = Depends(get_current_user)):
    """Get status of all registered agents."""
    try:
        orch = _get_orchestrator()
        return {"agents": orch.list_agents()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
def get_recent_events(
    limit: int = 50,
    event_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get recent inter-agent events."""
    try:
        from src.agents.base_agent import EventBus
        bus = EventBus()
        return {"events": bus.get_recent_events(limit=limit, event_type=event_type)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications")
def get_notifications(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Get recent agent notifications (from the Alert/Notification agent)."""
    orch = _get_orchestrator()
    alert_agent = orch.get_agent("alert_notification")

    if alert_agent and hasattr(alert_agent, "get_notifications"):
        return {"notifications": alert_agent.get_notifications(limit=limit)}

    return {"notifications": []}


# ---------------------------------------------------------------------------
# Individual Agent Endpoints
# ---------------------------------------------------------------------------

@router.get("/{agent_name}")
def get_agent_status(
    agent_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Get detailed status for a specific agent."""
    orch = _get_orchestrator()
    agent = orch.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {
        "status": agent.get_status(),
        "run_history": agent.get_run_history(),
    }


@router.put("/{agent_name}/toggle")
def toggle_agent(
    agent_name: str,
    body: AgentToggleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Enable or disable a specific agent."""
    orch = _get_orchestrator()
    if body.enabled:
        success = orch.enable_agent(agent_name)
    else:
        success = orch.disable_agent(agent_name)

    if not success:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    return {"agent_name": agent_name, "enabled": body.enabled}


async def execute_cycle_in_background(cycle_type: str, report_type: Optional[str]):
    """Execute cycle in background without blocking HTTP threads."""
    orch = _get_orchestrator()
    try:
        if cycle_type == "monitoring":
            await orch.run_monitoring_cycle()
        elif cycle_type == "procurement":
            await orch.run_procurement_cycle()
        elif cycle_type == "full":
            await orch.run_full_cycle()
        elif cycle_type == "report":
            await orch.run_report_cycle(report_type or "daily_summary")
    except Exception as e:
        logger.error(f"Background cycle failed: {e}")


@router.post("/cycles/run")
async def run_agent_cycle(
    body: CycleRunRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Run a complete agent cycle in the background.
    
    Cycle types:
    - 'monitoring': Inventory Monitor → Alerts (quick check)
    - 'procurement': Monitor → Anomaly → Procurement → Alerts
    - 'full': All 7 agents in dependency order
    - 'report': Reporting → Alerts
    """
    orch = _get_orchestrator()

    if orch.is_running:
        raise HTTPException(
            status_code=400,
            detail="An agent cycle is already executing. Please wait for the current run to finish."
        )

    valid_types = ("monitoring", "procurement", "full", "report")
    if body.cycle_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cycle type: '{body.cycle_type}'. Choose from: {', '.join(valid_types)}"
        )

    # Queue background task
    background_tasks.add_task(
        execute_cycle_in_background,
        body.cycle_type,
        body.report_type
    )

    return {
        "status": "triggered",
        "message": f"{body.cycle_type.upper()} cycle triggered successfully in background."
    }


@router.post("/{agent_name}/run")
async def run_single_agent(
    agent_name: str,
    body: AgentRunRequest = AgentRunRequest(),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """Trigger a single agent run."""
    orch = _get_orchestrator()
    agent = orch.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    try:
        result = await orch.run_single_agent(agent_name, body.context)
        return result.to_dict()
    except Exception as e:
        logger.error(f"Agent run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_name}/history")
def get_agent_history(
    agent_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Get run history for a specific agent."""
    orch = _get_orchestrator()
    agent = orch.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {"agent_name": agent_name, "history": agent.get_run_history()}


# ---------------------------------------------------------------------------
# Cycle Endpoints
# ---------------------------------------------------------------------------



@router.get("/cycles/history")
def get_cycle_history(current_user: dict = Depends(get_current_user)):
    """Get history of past agent cycles."""
    orch = _get_orchestrator()
    return {
        "cycle_count": orch.cycle_count,
        "history": list(reversed(orch._cycle_history)),
    }
