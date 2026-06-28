import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Truck, PlusCircle, X, Loader2, Pencil, Trash2, RefreshCw } from 'lucide-react';
import { getSuppliers, createSupplier, updateSupplier, deleteSupplier } from '../services/api';
import WhatsAppButton from '../components/WhatsAppButton';
import toast from 'react-hot-toast';
import './Suppliers.css';

const EMPTY_FORM = {
  name: '', phone: '', whatsapp_number: '', email: '', address: '', notes: ''
};

export default function Suppliers() {
  const { t } = useTranslation();
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);   // null = add, object = edit
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSuppliers();
      setSuppliers(data.suppliers || []);
    } catch {
      toast.error('Failed to load suppliers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setEditing(null); setForm(EMPTY_FORM); setModalOpen(true); };
  const openEdit = (s) => {
    setEditing(s);
    setForm({
      name: s.name || '',
      phone: s.phone || '',
      whatsapp_number: s.whatsapp_number || '',
      email: s.email || '',
      address: s.address || '',
      notes: s.notes || '',
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error('Supplier name is required'); return; }
    setSubmitting(true);
    try {
      if (editing) {
        await updateSupplier(editing.id, form);
        toast.success('Supplier updated');
      } else {
        await createSupplier(form);
        toast.success('Supplier added');
      }
      setModalOpen(false);
      load();
    } catch (err) {
      toast.error(err.message || 'Failed to save supplier');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete supplier "${name}"?`)) return;
    try {
      await deleteSupplier(id);
      toast.success('Supplier deleted');
      load();
    } catch (err) {
      toast.error(err.message || 'Failed to delete supplier');
    }
  };

  return (
    <div className="suppliers-page">
      <div className="page-header">
        <div>
          <h1>{t('suppliers.title')}</h1>
          <p>{t('suppliers.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> {t('common.refresh')}
          </button>
          <button className="btn btn-primary" onClick={openAdd}>
            <PlusCircle size={16} /> {t('suppliers.addSupplier')}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-container"><Loader2 size={32} className="spin" /></div>
      ) : suppliers.length === 0 ? (
        <div className="empty-state">
          <Truck size={48} />
          <p>{t('suppliers.noSuppliers')}</p>
          <button className="btn btn-primary" onClick={openAdd}><PlusCircle size={16} /> {t('suppliers.addSupplier')}</button>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('suppliers.name')}</th>
                  <th>{t('suppliers.phone')}</th>
                  <th>{t('suppliers.email')}</th>
                  <th>{t('suppliers.address')}</th>
                  <th>{t('suppliers.whatsapp')}</th>
                  <th>{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map(s => (
                  <tr key={s.id}>
                    <td><strong>{s.name}</strong></td>
                    <td>{s.phone || '—'}</td>
                    <td>{s.email || '—'}</td>
                    <td className="address-cell">{s.address || '—'}</td>
                    <td>
                      <WhatsAppButton
                        phone={s.whatsapp_number || s.phone}
                        message={`Hi ${s.name}, this is a message from OptiStock Procurement.`}
                        label="Chat"
                      />
                    </td>
                    <td>
                      <div className="action-btns">
                        <button className="btn btn-ghost btn-sm" onClick={() => openEdit(s)} title="Edit">
                          <Pencil size={14} />
                        </button>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id, s.name)} title="Delete">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Add / Edit Modal ── */}
      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Truck size={20} />
                <h2>{editing ? 'Edit Supplier' : 'Add Supplier'}</h2>
              </div>
              <button className="btn-close" onClick={() => setModalOpen(false)}><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">Supplier Name *</label>
                    <input className="form-input" placeholder="e.g. Acme Electronics" value={form.name}
                      onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Phone</label>
                    <input className="form-input" placeholder="e.g. +91 98765 43210" value={form.phone}
                      onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">
                      WhatsApp Number
                      <span className="form-hint"> (digits + country code, e.g. 919876543210)</span>
                    </label>
                    <input className="form-input" placeholder="919876543210" value={form.whatsapp_number}
                      onChange={e => setForm(f => ({ ...f, whatsapp_number: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Email</label>
                    <input type="email" className="form-input" placeholder="supplier@example.com" value={form.email}
                      onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
                  </div>
                  <div className="form-group form-group-full">
                    <label className="form-label">Address</label>
                    <input className="form-input" placeholder="City, State" value={form.address}
                      onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
                  </div>
                  <div className="form-group form-group-full">
                    <label className="form-label">Notes</label>
                    <textarea className="form-input" rows={3} placeholder="Any extra details…" value={form.notes}
                      onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : (editing ? 'Update' : 'Add Supplier')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
