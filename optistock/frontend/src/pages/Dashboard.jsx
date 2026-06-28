import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Package, AlertTriangle, IndianRupee, ShieldAlert,
  Loader2, X, Mail, ArrowRight, Clock, ShoppingCart, TrendingUp
} from 'lucide-react';
import StatsCard from '../components/StatsCard';
import InventoryTable from '../components/InventoryTable';
import EmailModal from '../components/EmailModal';
import QuickSalesModal from '../components/QuickSalesModal';
import { getInventory, getProfitSummary } from '../services/api';
import toast from 'react-hot-toast';
import './Dashboard.css';

function Dashboard() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewItem, setViewItem] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTarget, setEmailTarget] = useState(null);
  const [quickSaleOpen, setQuickSaleOpen] = useState(false);
  const [profit, setProfit] = useState(null);

  useEffect(() => {
    fetchInventory();
    getProfitSummary().then(setProfit).catch(() => {});
  }, []);

  const fetchInventory = async () => {
    try {
      const data = await getInventory();
      setInventory(data.items || []);
    } catch (error) {
      toast.error('Failed to load inventory');
    } finally {
      setLoading(false);
    }
  };

  const criticalItems = inventory.filter(i => i.risk_level === 'Critical');
  const highItems = inventory.filter(i => i.risk_level === 'High');
  const riskyItems = [...criticalItems, ...highItems];

  const stats = {
    totalProducts: inventory.length,
    criticalAlerts: criticalItems.length,
    highRisk: highItems.length,
    totalValue: inventory.reduce(
      (sum, item) => sum + (item.current_stock || 0) * (item.cost_per_unit || 0), 0
    ),
  };

  const handleEmailSupplier = (item) => {
    setEmailTarget(item);
    setEmailModalOpen(true);
  };

  const handleAnalyze = (sku) => {
    navigate(`/analysis?sku=${encodeURIComponent(sku)}`);
  };

  if (loading) {
    return (
      <div className="loading-container">
        <Loader2 size={40} className="spin" />
        <p>{t('dashboard.loading')}</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="page-header">
        <div>
          <h1>{t('dashboard.title')}</h1>
          <p>{t('dashboard.subtitle')}</p>
        </div>
        <button className="btn btn-primary" onClick={() => setQuickSaleOpen(true)}>
          <ShoppingCart size={16} /> {t('dashboard.quickSale')}
        </button>
      </div>

      <div className="stats-grid">
        <StatsCard title={t('dashboard.totalProducts')} value={stats.totalProducts} icon={Package} color="blue" subtitle={t('dashboard.uniqueSkus')} />
        <StatsCard
          title={t('dashboard.criticalAlerts')} value={stats.criticalAlerts} icon={AlertTriangle}
          color={stats.criticalAlerts > 0 ? 'red' : 'green'}
          subtitle={t('dashboard.mayRunOut')}
          trend={stats.criticalAlerts > 0 ? 'up' : 'down'}
          trendValue={stats.criticalAlerts > 0 ? t('dashboard.urgent') : t('dashboard.allClear')}
        />
        <StatsCard
          title={t('dashboard.highRisk')} value={stats.highRisk} icon={ShieldAlert}
          color={stats.highRisk > 0 ? 'yellow' : 'green'}
          subtitle={t('dashboard.stockTight')}
        />
        <StatsCard
          title={t('dashboard.inventoryValue')}
          value={`₹${stats.totalValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          icon={IndianRupee} color="green" subtitle={t('dashboard.totalStockValue')}
        />
        {profit && profit.has_selling_prices ? (
          <StatsCard
            title={t('dashboard.profit30Day')}
            value={`₹${(profit.total_profit || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
            icon={TrendingUp} color={profit.total_profit >= 0 ? 'green' : 'red'}
            subtitle={`${t('dashboard.margin')}: ${profit.margin_pct || 0}%`}
          />
        ) : (
          <StatsCard
            title={t('dashboard.profit30Day')}
            value="—"
            icon={TrendingUp} color="blue"
            subtitle={t('dashboard.setSellingPrices')}
          />
        )}
      </div>

      {riskyItems.length > 0 && (
        <div className="risk-section">
          <div className="section-header">
            <div className="section-title">
              <AlertTriangle size={20} />
              <h2>{t('dashboard.itemsRequiringAttention')}</h2>
              <span className="count-badge">{riskyItems.length}</span>
            </div>
          </div>
          <div className="risk-grid">
            {riskyItems.map((item) => (
              <div key={item.sku} className={`risk-card ${item.risk_level?.toLowerCase()}`}>
                <div className="risk-card-header">
                  <span className="risk-card-sku">{item.sku}</span>
                  <span className={`risk-badge ${item.risk_level?.toLowerCase()}`}>{item.risk_level}</span>
                </div>
                <h3 className="risk-card-name">{item.product_name}</h3>
                <div className="risk-card-metrics">
                  <div className="risk-metric">
                    <Package size={14} />
                    <span>{item.current_stock} units</span>
                  </div>
                  <div className="risk-metric">
                    <Clock size={14} />
                    <span>{item.days_of_stock >= 999 ? 'No sales data' : `${Math.round(item.days_of_stock)}d left`}</span>
                  </div>
                </div>
                <div className="risk-card-supplier">{t('dashboard.supplier')}: {item.supplier || t('common.unknown')}</div>
                <div className="risk-card-actions">
                  <button className="btn btn-danger btn-sm" onClick={() => handleEmailSupplier(item)}>
                    <Mail size={14} /> {t('dashboard.emailSupplier')}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleAnalyze(item.sku)}>
                    {t('dashboard.analyze')} <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="table-section">
        <div className="section-header">
          <div className="section-title">
            <Package size={20} />
            <h2>{t('dashboard.allInventory')}</h2>
          </div>
        </div>
        <div className="card">
          <InventoryTable
            data={inventory}
            onAnalyze={handleAnalyze}
            onView={(item) => setViewItem(item)}
            onEmail={handleEmailSupplier}
          />
        </div>
      </div>

      {viewItem && (
        <div className="modal-overlay" onClick={() => setViewItem(null)}>
          <div className="modal view-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{t('dashboard.productDetails')}</h2>
              <button className="btn-close" onClick={() => setViewItem(null)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              <div className="view-details">
                <div className="detail-row"><span className="detail-label">SKU</span><span className="detail-value sku-badge">{viewItem.sku}</span></div>
                <div className="detail-row"><span className="detail-label">Product Name</span><span className="detail-value">{viewItem.product_name || '-'}</span></div>
                <div className="detail-row"><span className="detail-label">Category</span><span className="detail-value">{viewItem.category || '-'}</span></div>
                <div className="detail-row"><span className="detail-label">Current Stock</span><span className="detail-value">{viewItem.current_stock?.toLocaleString() || 0} units</span></div>
                <div className="detail-row"><span className="detail-label">Cost Per Unit</span><span className="detail-value">₹{viewItem.cost_per_unit?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '0.00'}</span></div>
                <div className="detail-row"><span className="detail-label">Supplier</span><span className="detail-value">{viewItem.supplier || '-'}</span></div>
                <div className="detail-row"><span className="detail-label">Lead Time</span><span className="detail-value">{viewItem.lead_time_days || 0} days</span></div>
                <div className="detail-row"><span className="detail-label">Days of Stock</span><span className="detail-value">{viewItem.days_of_stock >= 999 ? 'N/A' : `${Math.round(viewItem.days_of_stock)} days`}</span></div>
                <div className="detail-row"><span className="detail-label">Risk Level</span><span className={`detail-value risk-text-${viewItem.risk_level?.toLowerCase()}`}>{viewItem.risk_level || 'N/A'}</span></div>
                <div className="detail-row"><span className="detail-label">Total Value</span><span className="detail-value highlight">₹{((viewItem.current_stock || 0) * (viewItem.cost_per_unit || 0)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span></div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setViewItem(null)}>Close</button>
              <button className="btn btn-primary" onClick={() => { setViewItem(null); handleAnalyze(viewItem.sku); }}>Run AI Analysis</button>
            </div>
          </div>
        </div>
      )}

      <EmailModal
        isOpen={emailModalOpen}
        onClose={() => { setEmailModalOpen(false); setEmailTarget(null); }}
        emailData={emailTarget ? {
          subject: `Urgent: Restock Request for ${emailTarget.product_name} (${emailTarget.sku})`,
          body: `Dear ${emailTarget.supplier || 'Supplier'},\n\nWe need to urgently restock ${emailTarget.product_name} (SKU: ${emailTarget.sku}).\n\nCurrent stock: ${emailTarget.current_stock} units\nEstimated days remaining: ${emailTarget.days_of_stock >= 999 ? 'N/A' : Math.round(emailTarget.days_of_stock) + ' days'}\nRisk Level: ${emailTarget.risk_level}\n\nPlease confirm availability and earliest delivery date.\n\nBest regards,\nOptiStock Procurement`
        } : null}
        sku={emailTarget?.sku}
      />

      <QuickSalesModal
        isOpen={quickSaleOpen}
        onClose={() => setQuickSaleOpen(false)}
        onSaleRecorded={fetchInventory}
      />
    </div>
  );
}

export default Dashboard;
