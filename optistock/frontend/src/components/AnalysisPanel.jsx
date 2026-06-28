import React, { useState } from 'react';
import {
  Brain,
  CheckCircle,
  AlertTriangle,
  Package,
  TrendingUp,
  Clock,
  Mail,
  Loader2,
  RefreshCw
} from 'lucide-react';
import ForecastChart from './ForecastChart';
import EmailModal from './EmailModal';
import { analyzeSku, enhancedAnalyzeSku, getForecast } from '../services/api';
import toast from 'react-hot-toast';
import './AnalysisPanel.css';

function AnalysisPanel({ selectedSku, onClose }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);

  const runAnalysis = async () => {
    if (!selectedSku) return;

    setLoading(true);
    try {
      const [enhanced, forecast, v1] = await Promise.all([
        enhancedAnalyzeSku(selectedSku).catch(() => null),
        getForecast(selectedSku).catch(() => null),
        analyzeSku(selectedSku).catch(() => null),
      ]);

      setAnalysis({
        ...v1,
        explanation: enhanced?.explanation || null,
        reorderUrgency: enhanced?.reorderUrgency || null,
        recommendation: enhanced?.recommendation || null,
        days_of_stock: enhanced?.days_of_stock || null,
        avg_daily_sales: enhanced?.avg_daily_sales || null,
        forecastData: forecast?.plot_data || v1?.plot_data || [],
      });
      toast.success(`Analysis complete for ${selectedSku}`);
    } catch (error) {
      toast.error('Analysis failed');
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (selectedSku) {
      runAnalysis();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSku]);

  if (!selectedSku) {
    return (
      <div className="analysis-panel empty-state">
        <Brain size={48} />
        <h3>Select a Product</h3>
        <p>Choose a product from the list to run AI analysis</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="analysis-panel">
        <div className="loading-container">
          <Loader2 size={40} className="spin" />
          <p>Running AI analysis for {selectedSku}...</p>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="analysis-panel empty-state">
        <AlertTriangle size={48} />
        <h3>Analysis Failed</h3>
        <p>Could not analyze {selectedSku}</p>
        <button className="btn btn-primary" onClick={runAnalysis}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  const isRestock = analysis.decision === 'Restock';
  const urgencyClass = (analysis.reorderUrgency || '').toLowerCase();

  return (
    <div className="analysis-panel">
      <div className="analysis-header">
        <div className="analysis-title">
          <Brain size={24} />
          <div>
            <h2>AI Analysis: {analysis.sku}</h2>
            <p>{analysis.product_name}</p>
          </div>
        </div>
        <button className="btn btn-secondary" onClick={runAnalysis}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Decision Card */}
      <div className={`decision-card ${isRestock ? 'restock' : 'hold'}`}>
        <div className="decision-icon">
          {isRestock ? <AlertTriangle size={32} /> : <CheckCircle size={32} />}
        </div>
        <div className="decision-content">
          <span className="decision-label">Agent Decision</span>
          <h3 className="decision-value">{analysis.decision}</h3>
          <div className="confidence-bar">
            <div
              className="confidence-fill"
              style={{ width: `${(analysis.confidence_score || 0) * 100}%` }}
            />
          </div>
          <span className="confidence-text">
            {((analysis.confidence_score || 0) * 100).toFixed(0)}% Confidence
          </span>
        </div>
      </div>

      {/* Urgency Badge */}
      {analysis.reorderUrgency && (
        <div className={`urgency-card urgency-${urgencyClass}`}>
          <Clock size={18} />
          <span className="urgency-label">Reorder Urgency:</span>
          <span className="urgency-value">{analysis.reorderUrgency}</span>
        </div>
      )}

      {/* Metrics Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <Package size={20} />
          <div className="metric-content">
            <span className="metric-label">Current Stock</span>
            <span className="metric-value">{analysis.current_stock?.toLocaleString()}</span>
          </div>
        </div>
        <div className="metric-card">
          <TrendingUp size={20} />
          <div className="metric-content">
            <span className="metric-label">30-Day Forecast</span>
            <span className="metric-value">{analysis.forecasted_demand?.toLocaleString()}</span>
          </div>
        </div>
        <div className="metric-card">
          <AlertTriangle size={20} />
          <div className="metric-content">
            <span className="metric-label">Risk Level</span>
            <span className={`metric-value risk-${analysis.risk_assessment?.risk_level?.toLowerCase()}`}>
              {analysis.risk_assessment?.risk_level}
            </span>
          </div>
        </div>
      </div>

      {/* AI Explanation */}
      {analysis.explanation && (
        <div className="reasoning-card">
          <h4>AI Explanation</h4>
          <p>{analysis.explanation}</p>
        </div>
      )}

      {/* Recommendation */}
      {analysis.recommendation && (
        <div className="reasoning-card recommendation">
          <h4>Recommendation</h4>
          <p>{analysis.recommendation}</p>
        </div>
      )}

      {/* Agent Reasoning (v1 fallback) */}
      {!analysis.explanation && analysis.reasoning && (
        <div className="reasoning-card">
          <h4>Agent Reasoning</h4>
          <p>{analysis.reasoning}</p>
        </div>
      )}

      {/* Forecast Chart */}
      {analysis.forecastData && analysis.forecastData.length > 0 && (
        <ForecastChart data={analysis.forecastData} />
      )}

      {/* Email Draft */}
      {analysis.email_draft && (
        <div className="email-draft-card">
          <div className="email-draft-header">
            <div className="email-draft-title">
              <Mail size={20} />
              <h4>Generated Email Draft</h4>
            </div>
            <button
              className="btn btn-primary"
              onClick={() => setShowEmailModal(true)}
            >
              <Mail size={16} />
              Send Email
            </button>
          </div>
          <div className="email-preview">
            <div className="email-field">
              <span className="field-label">Subject:</span>
              <span className="field-value">{analysis.email_draft.subject}</span>
            </div>
            <div className="email-body-preview">
              {analysis.email_draft.body}
            </div>
          </div>
        </div>
      )}

      <EmailModal
        isOpen={showEmailModal}
        onClose={() => setShowEmailModal(false)}
        emailData={analysis.email_draft}
        sku={analysis.sku}
      />
    </div>
  );
}

export default AnalysisPanel;
