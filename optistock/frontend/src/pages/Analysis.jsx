import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Brain, Loader2, Search, Package } from 'lucide-react';
import { getInventory } from '../services/api';
import AnalysisPanel from '../components/AnalysisPanel';
import toast from 'react-hot-toast';
import './Analysis.css';

function Analysis() {
  const [searchParams] = useSearchParams();
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSku, setSelectedSku] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchInventory();
  }, []);

  // Pre-select SKU from URL param once inventory loads
  useEffect(() => {
    const skuParam = searchParams.get('sku');
    if (skuParam && inventory.length > 0) {
      const found = inventory.find(i => i.sku === skuParam);
      if (found) {
        setSelectedSku(skuParam);
      }
    }
  }, [searchParams, inventory]);

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

  const filteredInventory = inventory.filter(item => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      item.sku?.toLowerCase().includes(q) ||
      item.product_name?.toLowerCase().includes(q) ||
      item.category?.toLowerCase().includes(q)
    );
  });

  const getRiskClass = (level) => {
    switch (level?.toLowerCase()) {
      case 'critical': return 'critical';
      case 'high': return 'high';
      case 'medium': return 'medium';
      case 'low': return 'low';
      default: return 'pending';
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <Loader2 size={40} className="spin" />
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="analysis-page">
      <div className="page-header">
        <div>
          <h1>AI Analysis Center</h1>
          <p>Run autonomous procurement analysis on your inventory</p>
        </div>
      </div>

      <div className="analysis-layout">
        {/* SKU Selection Panel */}
        <div className="sku-list-card">
          <h3>
            <Brain size={18} />
            Select Product
          </h3>

          <div className="sku-search">
            <Search size={16} />
            <input
              type="text"
              placeholder="Search SKU or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="sku-list">
            {filteredInventory.map(item => (
              <div
                key={item.sku}
                className={`sku-item ${selectedSku === item.sku ? 'selected' : ''}`}
                onClick={() => setSelectedSku(item.sku)}
              >
                <div className="sku-info">
                  <span className="sku-code">{item.sku}</span>
                  <span className="sku-name">{item.product_name}</span>
                </div>
                <div className="sku-meta">
                  <span className={`risk-badge-sm ${getRiskClass(item.risk_level)}`}>
                    {item.risk_level || 'N/A'}
                  </span>
                  <div className="sku-stock-info">
                    <Package size={11} />
                    <span>{item.current_stock}</span>
                  </div>
                </div>
              </div>
            ))}
            {filteredInventory.length === 0 && (
              <div className="sku-empty">
                No products match your search
              </div>
            )}
          </div>
        </div>

        {/* Analysis Detail Panel */}
        <div className="analysis-detail">
          <AnalysisPanel
            selectedSku={selectedSku}
            onClose={() => setSelectedSku(null)}
          />
        </div>
      </div>
    </div>
  );
}

export default Analysis;
