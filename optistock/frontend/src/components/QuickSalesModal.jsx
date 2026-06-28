import React, { useState, useEffect } from 'react';
import { X, ShoppingCart, Loader2 } from 'lucide-react';
import { getInventory, recordSale } from '../services/api';
import toast from 'react-hot-toast';

export default function QuickSalesModal({ isOpen, onClose, onSaleRecorded }) {
  const [inventory, setInventory] = useState([]);
  const [sku, setSku] = useState('');
  const [quantity, setQuantity] = useState('');
  const [saleDate, setSaleDate] = useState(new Date().toISOString().split('T')[0]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingInventory, setLoadingInventory] = useState(false);

  // Load inventory SKUs when modal opens
  useEffect(() => {
    if (!isOpen) return;
    setLoadingInventory(true);
    getInventory()
      .then(data => setInventory(data.items || []))
      .catch(() => {})
      .finally(() => setLoadingInventory(false));
  }, [isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!sku || !quantity) return;
    const qty = parseInt(quantity, 10);
    if (isNaN(qty) || qty <= 0) {
      toast.error('Quantity must be a positive number');
      return;
    }
    setSubmitting(true);
    try {
      await recordSale(sku, qty, saleDate);
      toast.success(`Sale recorded: ${qty} units of ${sku}`);
      setSku('');
      setQuantity('');
      setSaleDate(new Date().toISOString().split('T')[0]);
      if (onSaleRecorded) onSaleRecorded();
      onClose();
    } catch (err) {
      toast.error(err.message || 'Failed to record sale');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal quick-sale-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ShoppingCart size={20} />
            <h2>Record a Sale</h2>
          </div>
          <button className="btn-close" onClick={onClose}><X size={20} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {loadingInventory ? (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <Loader2 size={24} className="spin" />
              </div>
            ) : (
              <div className="form-grid">
                <div className="form-group">
                  <label className="form-label">Product (SKU)</label>
                  <select
                    className="form-input"
                    value={sku}
                    onChange={e => setSku(e.target.value)}
                    required
                  >
                    <option value="">-- Select product --</option>
                    {inventory.map(item => (
                      <option key={item.sku} value={item.sku}>
                        {item.sku} — {item.product_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Quantity Sold</label>
                  <input
                    type="number"
                    className="form-input"
                    value={quantity}
                    onChange={e => setQuantity(e.target.value)}
                    min={1}
                    placeholder="e.g. 10"
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Sale Date</label>
                  <input
                    type="date"
                    className="form-input"
                    value={saleDate}
                    onChange={e => setSaleDate(e.target.value)}
                    max={new Date().toISOString().split('T')[0]}
                  />
                </div>
              </div>
            )}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !sku || !quantity}>
              {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : 'Record Sale'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
