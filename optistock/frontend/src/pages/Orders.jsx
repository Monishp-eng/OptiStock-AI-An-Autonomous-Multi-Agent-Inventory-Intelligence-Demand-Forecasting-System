import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ClipboardList, PlusCircle, X, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { getOrders, createOrder, updateOrderStatus, deleteOrder, getInventory, getSuppliers } from '../services/api';
import toast from 'react-hot-toast';
import './Orders.css';

const STATUS_COLORS = {
  pending:   'status-pending',
  ordered:   'status-ordered',
  received:  'status-received',
  cancelled: 'status-cancelled',
};

const EMPTY_FORM = {
  sku: '', supplier_id: '', quantity: '', unit_cost: '', expected_delivery_at: '', notes: ''
};

export default function Orders() {
  const { t } = useTranslation();
  const [orders, setOrders] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ordersData, invData, supData] = await Promise.all([
        getOrders(statusFilter || undefined),
        getInventory(),
        getSuppliers(),
      ]);
      setOrders(ordersData.orders || []);
      setInventory(invData.items || []);
      setSuppliers(supData.suppliers || []);
    } catch {
      toast.error('Failed to load orders');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.sku || !form.quantity) { toast.error('SKU and quantity are required'); return; }
    setSubmitting(true);
    try {
      await createOrder({
        sku: form.sku,
        supplier_id: form.supplier_id ? parseInt(form.supplier_id) : null,
        quantity: parseInt(form.quantity),
        unit_cost: form.unit_cost ? parseFloat(form.unit_cost) : null,
        expected_delivery_at: form.expected_delivery_at || null,
        notes: form.notes || null,
      });
      toast.success('Order created');
      setModalOpen(false);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      toast.error(err.message || 'Failed to create order');
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      await updateOrderStatus(id, newStatus);
      toast.success(`Order marked as ${newStatus}`);
      load();
    } catch (err) {
      toast.error(err.message || 'Failed to update status');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this order?')) return;
    try {
      await deleteOrder(id);
      toast.success('Order deleted');
      load();
    } catch (err) {
      toast.error(err.message || 'Failed to delete order');
    }
  };

  return (
    <div className="orders-page">
      <div className="page-header">
        <div>
          <h1>{t('orders.title')}</h1>
          <p>{t('orders.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> {t('common.refresh')}
          </button>
          <button className="btn btn-primary" onClick={() => { setForm(EMPTY_FORM); setModalOpen(true); }}>
            <PlusCircle size={16} /> {t('orders.newOrder')}
          </button>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="status-tabs">
        {['', 'pending', 'ordered', 'received', 'cancelled'].map(s => (
          <button
            key={s}
            className={`status-tab ${statusFilter === s ? 'active' : ''}`}
            onClick={() => setStatusFilter(s)}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-container"><Loader2 size={32} className="spin" /></div>
      ) : orders.length === 0 ? (
        <div className="empty-state">
          <ClipboardList size={48} />
          <p>No orders found.</p>
          <button className="btn btn-primary" onClick={() => setModalOpen(true)}>
            <PlusCircle size={16} /> Create First Order
          </button>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>SKU</th>
                  <th>Qty</th>
                  <th>Unit Cost</th>
                  <th>Total</th>
                  <th>Status</th>
                  <th>Expected</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.id}>
                    <td>#{o.id}</td>
                    <td><span className="sku-badge">{o.sku}</span></td>
                    <td>{o.quantity}</td>
                    <td>{o.unit_cost != null ? `₹${o.unit_cost}` : '—'}</td>
                    <td>{o.total_cost != null ? `₹${o.total_cost}` : '—'}</td>
                    <td>
                      <select
                        className={`status-select ${STATUS_COLORS[o.status] || ''}`}
                        value={o.status}
                        onChange={e => handleStatusChange(o.id, e.target.value)}
                      >
                        <option value="pending">Pending</option>
                        <option value="ordered">Ordered</option>
                        <option value="received">Received</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                    </td>
                    <td>{o.expected_delivery_at ? o.expected_delivery_at.slice(0, 10) : '—'}</td>
                    <td>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(o.id)} title="Delete">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── New Order Modal ── */}
      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <ClipboardList size={20} />
                <h2>New Purchase Order</h2>
              </div>
              <button className="btn-close" onClick={() => setModalOpen(false)}><X size={20} /></button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="modal-body">
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">Product (SKU) *</label>
                    <select className="form-input" value={form.sku}
                      onChange={e => setForm(f => ({ ...f, sku: e.target.value }))} required>
                      <option value="">-- Select product --</option>
                      {inventory.map(i => (
                        <option key={i.sku} value={i.sku}>{i.sku} — {i.product_name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Supplier</label>
                    <select className="form-input" value={form.supplier_id}
                      onChange={e => setForm(f => ({ ...f, supplier_id: e.target.value }))}>
                      <option value="">-- Select supplier --</option>
                      {suppliers.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Quantity *</label>
                    <input type="number" className="form-input" min={1} placeholder="e.g. 100"
                      value={form.quantity} onChange={e => setForm(f => ({ ...f, quantity: e.target.value }))} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Unit Cost (₹)</label>
                    <input type="number" className="form-input" step="0.01" min={0} placeholder="e.g. 250.00"
                      value={form.unit_cost} onChange={e => setForm(f => ({ ...f, unit_cost: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Expected Delivery</label>
                    <input type="date" className="form-input"
                      value={form.expected_delivery_at}
                      onChange={e => setForm(f => ({ ...f, expected_delivery_at: e.target.value }))} />
                  </div>
                  <div className="form-group form-group-full">
                    <label className="form-label">Notes</label>
                    <textarea className="form-input" rows={2} placeholder="Special instructions…"
                      value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? <><Loader2 size={16} className="spin" /> Creating…</> : 'Create Order'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
