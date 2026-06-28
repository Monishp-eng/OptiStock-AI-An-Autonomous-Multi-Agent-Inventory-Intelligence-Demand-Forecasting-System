# src/agents/base_agent.py
"""
Base Agent class for the OptiStock Multi-Agent System.
All specialized agents inherit from this class.
Provides: Gemini AI access, event pub/sub, logging, run lifecycle.
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Gemini AI Configuration (shared across all agents)
# ---------------------------------------------------------------------------
try:
    import google.generativeai as genai

    _api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if _api_key:
        genai.configure(api_key=_api_key)
        GENAI_AVAILABLE = True
    else:
        GENAI_AVAILABLE = False
except ImportError:
    GENAI_AVAILABLE = False
    genai = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AgentEvent:
    """Event published by an agent for inter-agent communication."""
    event_type: str                     # e.g. "STOCK_CRITICAL", "ANOMALY_DETECTED"
    source_agent: str                   # Name of the agent that published
    timestamp: str = ""                 # ISO timestamp
    data: Dict[str, Any] = field(default_factory=dict)
    priority: str = "medium"            # low, medium, high, critical

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "timestamp": self.timestamp,
            "data": self.data,
            "priority": self.priority,
        }


@dataclass
class AgentResult:
    """Result returned by an agent after a run."""
    agent_name: str
    status: str                         # "success" or "error"
    timestamp: str = ""
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    events_published: List[AgentEvent] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "details": self.details,
            "events_published": [e.to_dict() for e in self.events_published],
            "actions_taken": self.actions_taken,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# In-process Event Bus (lightweight pub/sub for inter-agent communication)
# ---------------------------------------------------------------------------

class EventBus:
    """
    Simple in-process event bus for agent communication.
    In production, replace with Google Cloud Pub/Sub.
    """
    _instance = None
    _subscribers: Dict[str, List[Callable]] = {}
    _event_log: List[AgentEvent] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._subscribers = {}
            cls._event_log = []
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def publish(self, event: AgentEvent):
        """Publish an event to all subscribers."""
        self._event_log.append(event)
        # Keep only last 500 events
        if len(self._event_log) > 500:
            self._event_log = self._event_log[-500:]

        callbacks = self._subscribers.get(event.event_type, [])
        # Also notify wildcard subscribers
        callbacks += self._subscribers.get("*", [])

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logging.getLogger("event_bus").error(
                    f"Event handler error for {event.event_type}: {e}"
                )

    def get_recent_events(self, limit: int = 50, event_type: str = None) -> List[dict]:
        """Get recent events, optionally filtered by type."""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events[-limit:]]

    def clear(self):
        """Clear all events and subscribers (for testing)."""
        self._subscribers.clear()
        self._event_log.clear()


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """
    Base class for all OptiStock agents.
    
    Provides:
    - Gemini AI model access (with fallback)
    - Event bus for inter-agent communication
    - Run lifecycle management (start → execute → complete)
    - Structured logging
    - Status tracking
    """

    def __init__(
        self,
        agent_name: str,
        description: str,
        system_prompt: str = "",
        model_name: str = "gemini-1.5-flash",
        enabled: bool = True,
    ):
        self.agent_name = agent_name
        self.description = description
        self.system_prompt = system_prompt
        self.model_name = model_name
        self.enabled = enabled

        self.logger = logging.getLogger(f"agent.{agent_name}")
        self.event_bus = EventBus()
        self.status = AgentStatus.IDLE if enabled else AgentStatus.DISABLED
        self.last_run: Optional[AgentResult] = None
        self.run_count = 0
        self.total_events_published = 0

        # Run history (keep last 20 runs)
        self._run_history: List[dict] = []

    # ---- Gemini AI access ------------------------------------------------

    def get_model(self):
        """Return a Gemini GenerativeModel instance (or None if unavailable)."""
        if not GENAI_AVAILABLE:
            return None
        try:
            return genai.GenerativeModel(self.model_name)
        except Exception as e:
            self.logger.error(f"Failed to create Gemini model: {e}")
            return None

    def call_gemini(self, prompt: str, as_json: bool = True) -> Optional[Any]:
        """
        Call Gemini with a prompt and optionally parse JSON response.
        Returns None on failure.
        """
        model = self.get_model()
        if model is None:
            self.logger.warning("Gemini unavailable — using fallback")
            return None

        try:
            response = model.generate_content(prompt)
            text = response.text.strip()

            # Strip markdown code fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            if as_json:
                return json.loads(text)
            return text
        except Exception as e:
            self.logger.error(f"Gemini call failed: {e}")
            return None

    # ---- Event pub/sub ---------------------------------------------------

    def publish_event(self, event_type: str, data: dict, priority: str = "medium"):
        """Publish an event to the event bus."""
        event = AgentEvent(
            event_type=event_type,
            source_agent=self.agent_name,
            data=data,
            priority=priority,
        )
        self.event_bus.publish(event)
        self.total_events_published += 1
        self.logger.info(f"📤 Published event: {event_type} (priority={priority})")
        return event

    def subscribe_to(self, event_type: str, handler: Callable):
        """Subscribe to events from other agents."""
        self.event_bus.subscribe(event_type, handler)
        self.logger.info(f"📥 Subscribed to: {event_type}")

    # ---- Run lifecycle ---------------------------------------------------

    async def run(self, context: Dict[str, Any] = None) -> AgentResult:
        """
        Execute the agent's main logic.
        Wraps execute() with lifecycle management.
        """
        if not self.enabled:
            return AgentResult(
                agent_name=self.agent_name,
                status="disabled",
                summary=f"Agent '{self.agent_name}' is disabled",
            )

        self.status = AgentStatus.RUNNING
        start_time = datetime.utcnow()
        self.logger.info(f"🚀 Agent '{self.agent_name}' starting run #{self.run_count + 1}")

        try:
            result = await self.execute(context or {})
            result.duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.status = AgentStatus.SUCCESS
            self.logger.info(
                f"✅ Agent '{self.agent_name}' completed in {result.duration_ms:.0f}ms — "
                f"{len(result.actions_taken)} actions, {len(result.events_published)} events"
            )
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.logger.error(f"❌ Agent '{self.agent_name}' failed: {e}")
            result = AgentResult(
                agent_name=self.agent_name,
                status="error",
                summary=f"Agent failed: {str(e)}",
                errors=[str(e)],
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )

        self.run_count += 1
        self.last_run = result

        # Store in history
        self._run_history.append(result.to_dict())
        if len(self._run_history) > 20:
            self._run_history = self._run_history[-20:]

        return result

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """
        Override this method in subclasses to implement agent-specific logic.
        """
        raise NotImplementedError(
            f"Agent '{self.agent_name}' must implement execute()"
        )

    # ---- Status & info ---------------------------------------------------

    def get_status(self) -> dict:
        """Get current agent status for the dashboard."""
        return {
            "agent_name": self.agent_name,
            "description": self.description,
            "status": self.status.value,
            "enabled": self.enabled,
            "run_count": self.run_count,
            "total_events_published": self.total_events_published,
            "last_run": self.last_run.to_dict() if self.last_run else None,
            "ai_available": GENAI_AVAILABLE,
        }

    def get_run_history(self) -> List[dict]:
        """Get recent run history."""
        return list(reversed(self._run_history))

    def enable(self):
        """Enable the agent."""
        self.enabled = True
        self.status = AgentStatus.IDLE
        self.logger.info(f"Agent '{self.agent_name}' enabled")

    def disable(self):
        """Disable the agent."""
        self.enabled = False
        self.status = AgentStatus.DISABLED
        self.logger.info(f"Agent '{self.agent_name}' disabled")
