import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  Bot, Play, Power, AlertTriangle, ShieldCheck, ShieldAlert,
  Loader2, RefreshCw, Layers, Bell, Activity, Clock,
  Package, ShoppingCart, Search, DollarSign, FileText, Users,
  Mail, MessageSquare, ExternalLink
} from 'lucide-react';
import {
  getAgentDashboard,
  toggleAgent,
  runAgent,
  runAgentCycle,
  getAgentEvents,
  getAgentNotifications
} from '../services/api';
import './AgentHub.css';

// Mapping agent name to icons and display titles
const AGENT_META = {
  inventory_monitor: {
    icon: Package,
    color: '#f093fb',
    title: 'Inventory Monitor',
  },
  alert_notification: {
    icon: Bell,
    color: '#ff9a9e',
    title: 'Alert & Notifications',
  },
  auto_procurement: {
    icon: ShoppingCart,
    color: '#4facfe',
    title: 'Auto-Procurement',
  },
  anomaly_detection: {
    icon: Search,
    color: '#fa709a',
    title: 'Anomaly Detector',
  },
  supplier_intelligence: {
    icon: Users,
    color: '#43e97b',
    title: 'Supplier Intelligence',
  },
  scheduled_reporting: {
    icon: FileText,
    color: '#fccb90',
    title: 'Scheduled Reporting',
  },
  dynamic_pricing: {
    icon: DollarSign,
    color: '#a18cd1',
    title: 'Dynamic Pricing',
  }
};

export default function AgentHub() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [events, setEvents] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningAgent, setRunningAgent] = useState(null);
  const [runningCycle, setRunningCycle] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      silentRefresh();
    }, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const dbData = await getAgentDashboard();
      const evData = await getAgentEvents(30);
      const notifData = await getAgentNotifications(20);
      setDashboard(dbData);
      setEvents(evData.events || []);
      setNotifications(notifData.notifications || []);
    } catch (err) {
      console.error(err);
      toast.error('Failed to load agent hub data');
    } finally {
      setLoading(false);
    }
  };

  const silentRefresh = async () => {
    try {
      const dbData = await getAgentDashboard();
      const evData = await getAgentEvents(30);
      const notifData = await getAgentNotifications(20);
      setDashboard(dbData);
      setEvents(evData.events || []);
      setNotifications(notifData.notifications || []);
    } catch (err) {
      console.warn('Silent refresh failed', err);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
    toast.success('Agent status refreshed');
  };

  const handleToggle = async (agentName, currentStatus) => {
    try {
      await toggleAgent(agentName, !currentStatus);
      toast.success(`${AGENT_META[agentName]?.title || agentName} has been ${!currentStatus ? 'enabled' : 'disabled'}`);
      silentRefresh();
    } catch (err) {
      toast.error('Failed to update agent status');
    }
  };

  const handleRunAgent = async (agentName) => {
    setRunningAgent(agentName);
    try {
      toast.loading(`Running ${AGENT_META[agentName]?.title || agentName}...`, { id: 'run-agent' });
      const result = await runAgent(agentName);
      if (result.status === 'success') {
        toast.success(`${AGENT_META[agentName]?.title || agentName} ran successfully: ${result.summary}`, { id: 'run-agent' });
      } else {
        toast.error(`Agent failed: ${result.summary || result.errors.join(', ')}`, { id: 'run-agent' });
      }
      loadData();
    } catch (err) {
      toast.error('Failed to trigger agent', { id: 'run-agent' });
    } finally {
      setRunningAgent(null);
    }
  };

  const handleRunCycle = async (cycleType) => {
    setRunningCycle(cycleType);
    try {
      toast.loading(`Executing ${cycleType.toUpperCase()} cycle in background...`, { id: 'run-cycle' });
      const result = await runAgentCycle(cycleType);
      if (result.status === 'triggered') {
        toast.success(result.message || `${cycleType.toUpperCase()} cycle started in background.`, { id: 'run-cycle' });
      } else {
        toast.success(`Cycle complete!`, { id: 'run-cycle' });
      }
      loadData();
    } catch (err) {
      toast.error(err.message || 'Failed to run cycle', { id: 'run-cycle' });
    } finally {
      setRunningCycle(null);
    }
  };

  if (loading && !dashboard) {
    return (
      <div className="agent-hub-loading">
        <Loader2 className="spin" size={48} />
        <p>Initializing agent networks...</p>
      </div>
    );
  }

  const { orchestrator, agents } = dashboard || { orchestrator: {}, agents: [] };

  return (
    <div className="agent-hub-container">
      {/* Header */}
      <div className="agent-hub-header">
        <div>
          <h1>🤖 Multi-Agent Automation Command Center</h1>
          <p className="subtitle">OptiStock orchestrates 7 specialized AI agents to autonomously manage supply chain workflows.</p>
        </div>
        <button className="btn-refresh" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className={refreshing ? 'spin' : ''} size={18} />
          <span>Refresh Hub</span>
        </button>
      </div>

      {/* Cycle running banner */}
      {orchestrator && orchestrator.is_running && (
        <div className="cycle-running-banner">
          <Loader2 className="spin" size={16} />
          <span>System cycle is currently executing in the background. Status updates will refresh automatically.</span>
        </div>
      )}

      {/* Overview stats */}
      <div className="agent-hub-overview">
        <div className="overview-card">
          <div className="card-icon blue"><Bot size={24} /></div>
          <div className="card-content">
            <h3>{orchestrator.enabled_agents} / {orchestrator.total_agents}</h3>
            <p>Active Agents</p>
          </div>
        </div>
        <div className="overview-card">
          <div className="card-icon purple"><Layers size={24} /></div>
          <div className="card-content">
            <h3>{orchestrator.cycle_count}</h3>
            <p>Scheduled Cycles Run</p>
          </div>
        </div>
        <div className="overview-card">
          <div className="card-icon green"><Activity size={24} /></div>
          <div className="card-content">
            <h3>{events.length}</h3>
            <p>Recent Event Triggers</p>
          </div>
        </div>
        <div className="overview-card">
          <div className="card-icon orange"><Bell size={24} /></div>
          <div className="card-content">
            <h3>{notifications.length}</h3>
            <p>Total Notifications</p>
          </div>
        </div>
      </div>

      {/* Cycle triggers */}
      <div className="cycle-trigger-section">
        <h2>🔄 Trigger System Execution Cycles</h2>
        <p>Manually run pipelines linking multiple agents in sequence.</p>
        <div className="cycle-buttons">
          <button 
            className="cycle-btn" 
            onClick={() => handleRunCycle('monitoring')}
            disabled={runningCycle !== null}
          >
            {runningCycle === 'monitoring' ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            <div>
              <strong>Quick Stock Audit</strong>
              <span>Scans stock levels & compiles alert notifications</span>
            </div>
          </button>
          <button 
            className="cycle-btn primary" 
            onClick={() => handleRunCycle('procurement')}
            disabled={runningCycle !== null}
          >
            {runningCycle === 'procurement' ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            <div>
              <strong>Auto-Procurement Cycle</strong>
              <span>Audit stock → anomaly check → draft POs → send alert</span>
            </div>
          </button>
          <button 
            className="cycle-btn success" 
            onClick={() => handleRunCycle('full')}
            disabled={runningCycle !== null}
          >
            {runningCycle === 'full' ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            <div>
              <strong>Daily Operations Cycle</strong>
              <span>Executes all 7 agents in full dependency sequence</span>
            </div>
          </button>
          <button 
            className="cycle-btn warning" 
            onClick={() => handleRunCycle('report')}
            disabled={runningCycle !== null}
          >
            {runningCycle === 'report' ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            <div>
              <strong>Generate Daily Digest</strong>
              <span>Assembles reporting payload and emails summaries</span>
            </div>
          </button>
        </div>
      </div>

      {/* Agents grid */}
      <div className="agents-grid-section">
        <h2>📋 Specialized AI Agent Directory</h2>
        <div className="agents-grid">
          {agents.map((agent) => {
            const meta = AGENT_META[agent.agent_name] || { icon: Bot, color: '#94a3b8', title: agent.agent_name };
            const AgentIcon = meta.icon;
            const lastRun = agent.last_run;

            return (
              <div 
                key={agent.agent_name} 
                className={`agent-card ${agent.status === 'running' ? 'running-pulse' : ''} ${!agent.enabled ? 'disabled-card' : ''}`}
                style={{ '--accent-color': meta.color }}
              >
                <div className="agent-card-header">
                  <div className="agent-avatar" style={{ backgroundColor: `${meta.color}20`, color: meta.color }}>
                    <AgentIcon size={20} />
                  </div>
                  <div>
                    <h3>{meta.title}</h3>
                    <span className={`status-badge ${agent.status}`}>
                      {agent.status.toUpperCase()}
                    </span>
                  </div>
                </div>

                <p className="agent-desc">{agent.description}</p>

                <div className="agent-stats">
                  <div className="stat-row">
                    <span>Runs Count:</span>
                    <strong>{agent.run_count}</strong>
                  </div>
                  <div className="stat-row">
                    <span>Events Fired:</span>
                    <strong>{agent.total_events_published}</strong>
                  </div>
                  {lastRun && (
                    <>
                      <div className="stat-row">
                        <span>Last Duration:</span>
                        <strong>{lastRun.duration_ms ? `${lastRun.duration_ms.toFixed(0)}ms` : '—'}</strong>
                      </div>
                      <div className="stat-row summary-row">
                        <span>Last Outcome:</span>
                        <span className="summary-text" title={lastRun.summary}>{lastRun.summary}</span>
                      </div>
                    </>
                  )}
                </div>

                <div className="agent-card-actions">
                  <button 
                    className={`btn-toggle ${agent.enabled ? 'enabled' : 'disabled'}`}
                    onClick={() => handleToggle(agent.agent_name, agent.enabled)}
                    title={agent.enabled ? 'Disable Agent' : 'Enable Agent'}
                  >
                    <Power size={14} />
                    <span>{agent.enabled ? 'Disable' : 'Enable'}</span>
                  </button>
                  <button 
                    className="btn-run"
                    onClick={() => handleRunAgent(agent.agent_name)}
                    disabled={!agent.enabled || runningAgent === agent.agent_name}
                  >
                    {runningAgent === agent.agent_name ? <Loader2 className="spin" size={14} /> : <Play size={14} />}
                    <span>Run Agent</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Notifications & Events section */}
      <div className="agent-feed-section">
        {/* Notifications */}
        <div className="feed-column">
          <h2>🔔 Live Actionable Alerts</h2>
          <div className="feed-box">
            {notifications.length === 0 ? (
              <p className="empty-feed">No actionable notifications found.</p>
            ) : (
              notifications.map((notif, idx) => (
                <div key={idx} className={`notif-item ${notif.priority}`}>
                  <div className="notif-header">
                    <strong>{notif.title}</strong>
                    <span className="notif-time">
                      <Clock size={12} />
                      {notif.timestamp.substring(11, 16)}
                    </span>
                  </div>
                  <p className="notif-msg">{notif.message}</p>
                  <div className="notif-meta">
                    <span className="source-tag">Agent: {AGENT_META[notif.source_agent]?.title || notif.source_agent}</span>
                    {notif.sku && <span className="sku-tag">SKU: {notif.sku}</span>}
                  </div>
                  {notif.whatsapp_link && (
                    <a 
                      href={notif.whatsapp_link} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="whatsapp-alert-btn"
                    >
                      <MessageSquare size={12} />
                      <span>Send Whatsapp Alert</span>
                      <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Live event logs */}
        <div className="feed-column">
          <h2>🔌 Inter-Agent Event Bus</h2>
          <div className="feed-box event-feed">
            {events.length === 0 ? (
              <p className="empty-feed">No active events logged on bus.</p>
            ) : (
              events.map((evt, idx) => (
                <div key={idx} className="event-item">
                  <div className="event-header">
                    <span className={`event-badge ${evt.priority}`}>{evt.event_type}</span>
                    <span className="event-time">{evt.timestamp.substring(11, 19)}</span>
                  </div>
                  <div className="event-details">
                    <span>Fired by: <strong>{AGENT_META[evt.source_agent]?.title || evt.source_agent}</strong></span>
                    {evt.data && evt.data.sku && (
                      <span>Item: <strong>{evt.data.product_name || evt.data.sku}</strong></span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
