import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Package, ShoppingCart, Brain, ChevronRight, Check, Loader2 } from 'lucide-react';
import { createInventoryItem, recordSale, getInventory } from '../services/api';
import toast from 'react-hot-toast';
import './Onboarding.css';

const STEPS = [
  { id: 1, icon: Package,      title: 'Add Your First Product',  desc: 'Enter a product you sell to get started' },
  { id: 2, icon: ShoppingCart, title: 'Record Initial Sales',     desc: 'Add a recent sale so forecasts work from day one' },
  { id: 3, icon: Brain,        title: 'You\'re Ready!',           desc: 'Head to the dashboard to see your inventory health' },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  // Step 1 form
  const [product, setProduct] = useState({
    sku: '', product_name: '', category: 'Electronics',
    current_stock: '', cost_per_unit: '', supplier: '', lead_time_days: 7
  });

  // Step 2 form
  const [skus, setSkus] = useState([]);
  const [saleForm, setSaleForm] = useState({ sku: '', quantity: '', saleDate: new Date().toISOString().split('T')[0] });

  const handleAddProduct = async (e) => {
    e.preventDefault();
    if (!product.sku || !product.product_name) { toast.error('SKU and product name are required'); return; }
    setSubmitting(true);
    try {
      await createInventoryItem({
        ...product,
        current_stock: parseInt(product.current_stock) || 0,
        cost_per_unit: parseFloat(product.cost_per_unit) || 0,
        lead_time_days: parseInt(product.lead_time_days) || 7,
      });
      toast.success(`Product "${product.product_name}" added!`);
      // Load SKUs for step 2
      const inv = await getInventory();
      setSkus((inv.items || []).map(i => ({ sku: i.sku, name: i.product_name })));
      setSaleForm(f => ({ ...f, sku: product.sku.toUpperCase() }));
      setStep(2);
    } catch (err) {
      toast.error(err.message || 'Failed to add product');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRecordSale = async (e) => {
    e.preventDefault();
    if (!saleForm.sku || !saleForm.quantity) { toast.error('Select a product and enter quantity'); return; }
    setSubmitting(true);
    try {
      await recordSale(saleForm.sku, parseInt(saleForm.quantity), saleForm.saleDate);
      toast.success('Sale recorded!');
      setStep(3);
    } catch (err) {
      toast.error(err.message || 'Failed to record sale');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="onboarding-page">
      <div className="onboarding-card">
        {/* Header */}
        <div className="onboarding-header">
          <div className="onboarding-logo">
            <Sparkles size={28} />
          </div>
          <h1>Welcome to OptiStock</h1>
          <p>Let's get your inventory set up in 3 quick steps</p>
        </div>

        {/* Step indicators */}
        <div className="step-indicators">
          {STEPS.map(s => (
            <div key={s.id} className={`step-dot ${step >= s.id ? 'done' : ''} ${step === s.id ? 'active' : ''}`}>
              {step > s.id ? <Check size={14} /> : s.id}
            </div>
          ))}
        </div>

        {/* Step content */}
        {step === 1 && (
          <form onSubmit={handleAddProduct} className="onboarding-form">
            <div className="step-header">
              <Package size={24} />
              <h2>Add Your First Product</h2>
            </div>
            <div className="form-grid-2">
              <div className="form-group">
                <label className="form-label">SKU *</label>
                <input className="form-input" placeholder="e.g. WIDGET-001" value={product.sku}
                  onChange={e => setProduct(p => ({ ...p, sku: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">Product Name *</label>
                <input className="form-input" placeholder="e.g. Blue Widget" value={product.product_name}
                  onChange={e => setProduct(p => ({ ...p, product_name: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">Category</label>
                <input className="form-input" placeholder="e.g. Electronics" value={product.category}
                  onChange={e => setProduct(p => ({ ...p, category: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Current Stock</label>
                <input type="number" className="form-input" placeholder="e.g. 500" min={0}
                  value={product.current_stock}
                  onChange={e => setProduct(p => ({ ...p, current_stock: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Cost per Unit (₹)</label>
                <input type="number" className="form-input" step="0.01" placeholder="e.g. 250" min={0}
                  value={product.cost_per_unit}
                  onChange={e => setProduct(p => ({ ...p, cost_per_unit: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Supplier</label>
                <input className="form-input" placeholder="e.g. Acme Corp"
                  value={product.supplier}
                  onChange={e => setProduct(p => ({ ...p, supplier: e.target.value }))} />
              </div>
            </div>
            <button type="submit" className="btn btn-primary btn-full" disabled={submitting}>
              {submitting ? <><Loader2 size={16} className="spin" /> Adding…</> : <>Next: Record a Sale <ChevronRight size={16} /></>}
            </button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleRecordSale} className="onboarding-form">
            <div className="step-header">
              <ShoppingCart size={24} />
              <h2>Record a Sale</h2>
            </div>
            <div className="form-group">
              <label className="form-label">Product</label>
              <select className="form-input" value={saleForm.sku}
                onChange={e => setSaleForm(f => ({ ...f, sku: e.target.value }))} required>
                <option value="">-- Select --</option>
                {skus.map(s => <option key={s.sku} value={s.sku}>{s.sku} — {s.name}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Quantity Sold</label>
              <input type="number" className="form-input" min={1} placeholder="e.g. 20"
                value={saleForm.quantity}
                onChange={e => setSaleForm(f => ({ ...f, quantity: e.target.value }))} required />
            </div>
            <div className="form-group">
              <label className="form-label">Sale Date</label>
              <input type="date" className="form-input" value={saleForm.saleDate}
                max={new Date().toISOString().split('T')[0]}
                onChange={e => setSaleForm(f => ({ ...f, saleDate: e.target.value }))} />
            </div>
            <div className="onboarding-btns">
              <button type="button" className="btn btn-ghost" onClick={() => setStep(3)}>Skip</button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : <>Record & Continue <ChevronRight size={16} /></>}
              </button>
            </div>
          </form>
        )}

        {step === 3 && (
          <div className="onboarding-complete">
            <div className="complete-icon"><Check size={40} /></div>
            <h2>All set!</h2>
            <p>Your inventory is ready. Head to the Dashboard to view your stock health, risk alerts, and AI-powered forecasts.</p>
            <button className="btn btn-primary btn-full" onClick={() => navigate('/dashboard')}>
              Go to Dashboard <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
