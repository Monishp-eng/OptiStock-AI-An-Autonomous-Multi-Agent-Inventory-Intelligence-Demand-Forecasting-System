import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Loader2, RefreshCw, X, Mail, Download, FileText } from 'lucide-react';
import InventoryTable from '../components/InventoryTable';
import EmailModal from '../components/EmailModal';
import { getInventory, createInventoryItem, downloadExcel, downloadPdf } from '../services/api';
import toast from 'react-hot-toast';
import './Inventory.css';

function Inventory() {
  const navigate = useNavigate();
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [viewItem, setViewItem] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTarget, setEmailTarget] = useState(null);
  const [newItem, setNewItem] = useState({
    sku: '',
    product_name: '',
    category: '',
    current_stock: 0,
    cost_per_unit: 0,
    selling_price: 0,
    supplier: '',
    defect_rate: 0.01,
    lead_time_days: 7
  });

  useEffect(() => {
    fetchInventory();
  }, []);

  const fetchInventory = async () => {
    setLoading(true);
    try {
      const data = await getInventory();
      setInventory(data.items || []);
    } catch (error) {
      toast.error('Failed to load inventory');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type } = e.target;
    setNewItem(prev => ({
      ...prev,
      [name]: type === 'number' ? parseFloat(value) || 0 : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!newItem.sku || !newItem.product_name) {
      toast.error('SKU and Product Name are required');
      return;
    }

    setSubmitting(true);
    try {
      await createInventoryItem(newItem);
      toast.success(`Product ${newItem.sku} added successfully!`);
      setShowAddModal(false);
      setNewItem({
        sku: '',
        product_name: '',
        category: '',
        current_stock: 0,
        cost_per_unit: 0,
        selling_price: 0,
        supplier: '',
        defect_rate: 0.01,
        lead_time_days: 7
      });
      fetchInventory();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add product');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAnalyze = (sku) => {
    navigate(`/analysis?sku=${encodeURIComponent(sku)}`);
  };

  const handleEmailSupplier = (item) => {
    setEmailTarget(item);
    setEmailModalOpen(true);
  };

  const handleExportExcel = async () => {
    try {
      const response = await downloadExcel();
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'inventory.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to export Excel');
    }
  };

  const handleExportPdf = async () => {
    try {
      const response = await downloadPdf();
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'inventory.pdf';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to export PDF');
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <Loader2 size={40} className="spin" />
        <p>Loading inventory...</p>
      </div>
    );
  }

  return (
    <div className="inventory-page">
      <div className="page-header">
        <div>
          <h1>Inventory Management</h1>
          <p>Manage your products and stock levels</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={fetchInventory}>
            <RefreshCw size={16} />
            Refresh
          </button>
          <button className="btn btn-secondary" onClick={handleExportExcel}>
            <Download size={16} />
            Excel
          </button>
          <button className="btn btn-secondary" onClick={handleExportPdf}>
            <FileText size={16} />
            PDF
          </button>
          <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
            <Plus size={16} />
            Add Product
          </button>
        </div>
      </div>

      <div className="table-section">
        <div className="card">
          <InventoryTable
            data={inventory}
            onAnalyze={handleAnalyze}
            onView={(item) => setViewItem(item)}
            onEmail={handleEmailSupplier}
          />
        </div>
      </div>

      {/* View Product Modal */}
      {viewItem && (
        <div className="modal-overlay" onClick={() => setViewItem(null)}>
          <div className="modal view-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Product Details</h2>
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
              {(viewItem.risk_level === 'Critical' || viewItem.risk_level === 'High') && (
                <button className="btn btn-danger" onClick={() => { setViewItem(null); handleEmailSupplier(viewItem); }}>
                  <Mail size={16} /> Email Supplier
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => setViewItem(null)}>Close</button>
              <button className="btn btn-primary" onClick={() => { setViewItem(null); handleAnalyze(viewItem.sku); }}>Run AI Analysis</button>
            </div>
          </div>
        </div>
      )}

      {/* Add Product Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add New Product</h2>
              <button className="btn-close" onClick={() => setShowAddModal(false)}>
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>SKU *</label>
                    <input
                      type="text"
                      name="sku"
                      className="input"
                      placeholder="e.g., SKU-006"
                      value={newItem.sku}
                      onChange={handleInputChange}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Category</label>
                    <input
                      type="text"
                      name="category"
                      className="input"
                      placeholder="e.g., Electronics"
                      value={newItem.category}
                      onChange={handleInputChange}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Product Name *</label>
                  <input
                    type="text"
                    name="product_name"
                    className="input"
                    placeholder="e.g., Wireless Headphones"
                    value={newItem.product_name}
                    onChange={handleInputChange}
                    required
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Current Stock</label>
                    <input
                      type="number"
                      name="current_stock"
                      className="input"
                      min="0"
                      value={newItem.current_stock}
                      onChange={handleInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label>Cost Per Unit (₹)</label>
                    <input
                      type="number"
                      name="cost_per_unit"
                      className="input"
                      min="0"
                      step="0.01"
                      value={newItem.cost_per_unit}
                      onChange={handleInputChange}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Selling Price (₹)</label>
                    <input
                      type="number"
                      name="selling_price"
                      className="input"
                      min="0"
                      step="0.01"
                      value={newItem.selling_price}
                      onChange={handleInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label>Supplier</label>
                    <input
                      type="text"
                      name="supplier"
                      className="input"
                      placeholder="e.g., Tech Supplies Inc."
                      value={newItem.supplier}
                      onChange={handleInputChange}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Defect Rate (0-1)</label>
                    <input
                      type="number"
                      name="defect_rate"
                      className="input"
                      min="0"
                      max="1"
                      step="0.001"
                      value={newItem.defect_rate}
                      onChange={handleInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label>Lead Time (Days)</label>
                    <input
                      type="number"
                      name="lead_time_days"
                      className="input"
                      min="1"
                      value={newItem.lead_time_days}
                      onChange={handleInputChange}
                    />
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowAddModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Loader2 size={16} className="spin" />
                      Adding...
                    </>
                  ) : (
                    <>
                      <Plus size={16} />
                      Add Product
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Email Modal */}
      <EmailModal
        isOpen={emailModalOpen}
        onClose={() => { setEmailModalOpen(false); setEmailTarget(null); }}
        emailData={emailTarget ? {
          subject: `Urgent: Restock Request for ${emailTarget.product_name} (${emailTarget.sku})`,
          body: `Dear ${emailTarget.supplier || 'Supplier'},\n\nWe need to urgently restock ${emailTarget.product_name} (SKU: ${emailTarget.sku}).\n\nCurrent stock: ${emailTarget.current_stock} units\nEstimated days remaining: ${emailTarget.days_of_stock >= 999 ? 'N/A' : Math.round(emailTarget.days_of_stock) + ' days'}\nRisk Level: ${emailTarget.risk_level}\n\nPlease confirm availability and earliest delivery date.\n\nBest regards,\nOptiStock Procurement`
        } : null}
        sku={emailTarget?.sku}
      />
    </div>
  );
}

export default Inventory;
