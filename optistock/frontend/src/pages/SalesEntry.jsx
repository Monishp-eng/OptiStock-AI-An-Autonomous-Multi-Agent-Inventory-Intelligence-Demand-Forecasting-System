import React, { useState, useEffect, useCallback } from 'react';
import { ShoppingCart, Loader2, PlusCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { recordSale, getSales, getInventory } from '../services/api';
import toast from 'react-hot-toast';
import './SalesEntry.css';

export default function SalesEntry() {
  const { t } = useTranslation();
  const [inventory, setInventory] = useState([]);
  const [sales, setSales] = useState([]);
  const [loadingSales, setLoadingSales] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const [sku, setSku] = useState('');
  const [quantity, setQuantity] = useState('');
  const [saleDate, setSaleDate] = useState(new Date().toISOString().split('T')[0]);

  const loadData = useCallback(async () => {
    setLoadingSales(true);
    try {
      const [invData, salesData] = await Promise.all([getInventory(), getSales()]);
      setInventory(invData.items || []);
      setSales(salesData.sales || []);
    } catch {
      toast.error('Failed to load data');
    } finally {
      setLoadingSales(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const qty = parseInt(quantity, 10);
    if (!sku) { toast.error('Select a product'); return; }
    if (isNaN(qty) || qty <= 0) { toast.error('Enter a valid quantity'); return; }

    setSubmitting(true);
    try {
      await recordSale(sku, qty, saleDate);
      toast.success(`Recorded: ${qty} units of ${sku}`);
      setSku('');
      setQuantity('');
      setSaleDate(new Date().toISOString().split('T')[0]);
      loadData();
    } catch (err) {
      toast.error(err.message || 'Failed to record sale');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="sales-page">
      <div className="page-header">
        <div>
          <h1>{t('sales.title')}</h1>
          <p>{t('sales.subtitle')}</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={loadData} disabled={loadingSales}>
          <RefreshCw size={16} className={loadingSales ? 'spin' : ''} />
          {t('common.refresh')}
        </button>
      </div>

      {/* ── Entry Form ─────────────────────────────────────────── */}
      <div className="card sales-form-card">
        <div className="card-title">
          <PlusCircle size={20} />
          <h2>{t('sales.newSale')}</h2>
        </div>
        <form onSubmit={handleSubmit} className="sales-form">
          <div className="form-group">
            <label className="form-label">{t('sales.productSKU')}</label>
            <select className="form-input" value={sku} onChange={e => setSku(e.target.value)} required>
              <option value="">{t('sales.selectProduct')}</option>
              {inventory.map(item => (
                <option key={item.sku} value={item.sku}>
                  {item.sku} — {item.product_name} ({t('common.stock')}: {item.current_stock})
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{t('sales.quantitySold')}</label>
            <input
              type="number" className="form-input" value={quantity}
              onChange={e => setQuantity(e.target.value)} min={1} placeholder="e.g. 5" required
            />
          </div>
          <div className="form-group">
            <label className="form-label">{t('sales.saleDate')}</label>
            <input
              type="date" className="form-input" value={saleDate}
              onChange={e => setSaleDate(e.target.value)}
              max={new Date().toISOString().split('T')[0]}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? <><Loader2 size={16} className="spin" /> {t('sales.saving')}</> : <><ShoppingCart size={16} /> {t('sales.recordSale')}</>}
          </button>
        </form>
      </div>

      {/* ── Sales History ──────────────────────────────────────── */}
      <div className="card">
        <div className="card-title">
          <ShoppingCart size={20} />
          <h2>{t('sales.recentSales')}</h2>
          <span className="count-badge">{sales.length}</span>
        </div>
        {loadingSales ? (
          <div className="loading-container"><Loader2 size={32} className="spin" /></div>
        ) : sales.length === 0 ? (
          <div className="empty-state">
            <ShoppingCart size={48} />
            <p>{t('sales.noSalesYet')}</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('sales.date')}</th>
                  <th>SKU</th>
                  <th>{t('sales.product')}</th>
                  <th>{t('sales.qtySold')}</th>
                </tr>
              </thead>
              <tbody>
                {sales.slice().reverse().map((sale, idx) => (
                  <tr key={idx}>
                    <td>{sale.sale_date ? sale.sale_date.slice(0, 10) : '—'}</td>
                    <td><span className="sku-badge">{sale.sku}</span></td>
                    <td>{sale.product_name || sale.sku}</td>
                    <td>{sale.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
