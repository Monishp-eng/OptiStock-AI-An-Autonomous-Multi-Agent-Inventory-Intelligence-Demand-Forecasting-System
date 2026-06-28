import React, { useState, useMemo } from 'react';
import { Search, ChevronUp, ChevronDown, Eye, Brain, Mail } from 'lucide-react';
import './InventoryTable.css';

function InventoryTable({ data, onAnalyze, onView, onEmail }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'sku', direction: 'asc' });

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const filteredAndSortedData = useMemo(() => {
    const riskOrder = { Critical: 0, High: 1, Medium: 2, Low: 3 };
    let result = [...data];

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(item =>
        item.sku?.toLowerCase().includes(term) ||
        item.product_name?.toLowerCase().includes(term) ||
        item.category?.toLowerCase().includes(term) ||
        item.supplier?.toLowerCase().includes(term)
      );
    }

    result.sort((a, b) => {
      if (sortConfig.key === 'risk_level') {
        const aVal = riskOrder[a.risk_level] ?? 99;
        const bVal = riskOrder[b.risk_level] ?? 99;
        return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
      }

      const aVal = a[sortConfig.key] ?? '';
      const bVal = b[sortConfig.key] ?? '';

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      return sortConfig.direction === 'asc'
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });

    return result;
  }, [data, searchTerm, sortConfig]);

  const getRiskBadgeClass = (riskLevel) => {
    switch (riskLevel) {
      case 'Critical': return 'danger';
      case 'High': return 'warning';
      case 'Medium': return 'info';
      case 'Low': return 'success';
      default: return 'info';
    }
  };

  const getStockStatus = (stock) => {
    if (stock <= 50) return { label: 'Low', class: 'danger' };
    if (stock <= 150) return { label: 'Medium', class: 'warning' };
    return { label: 'Good', class: 'success' };
  };

  const SortIcon = ({ columnKey }) => {
    if (sortConfig.key !== columnKey) {
      return <ChevronUp size={14} className="sort-icon inactive" />;
    }
    return sortConfig.direction === 'asc'
      ? <ChevronUp size={14} className="sort-icon" />
      : <ChevronDown size={14} className="sort-icon" />;
  };

  return (
    <div className="inventory-table-container">
      <div className="table-toolbar">
        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search by SKU, product, category..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input"
          />
        </div>
        <div className="table-info">
          Showing {filteredAndSortedData.length} of {data.length} items
        </div>
      </div>

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th onClick={() => handleSort('sku')}>
                SKU <SortIcon columnKey="sku" />
              </th>
              <th onClick={() => handleSort('product_name')}>
                Product <SortIcon columnKey="product_name" />
              </th>
              <th onClick={() => handleSort('category')}>
                Category <SortIcon columnKey="category" />
              </th>
              <th onClick={() => handleSort('current_stock')}>
                Stock <SortIcon columnKey="current_stock" />
              </th>
              <th onClick={() => handleSort('days_of_stock')}>
                Days Left <SortIcon columnKey="days_of_stock" />
              </th>
              <th onClick={() => handleSort('supplier')}>
                Supplier <SortIcon columnKey="supplier" />
              </th>
              <th onClick={() => handleSort('risk_level')}>
                Risk <SortIcon columnKey="risk_level" />
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredAndSortedData.length === 0 ? (
              <tr>
                <td colSpan="8" className="empty-row">
                  No inventory items found
                </td>
              </tr>
            ) : (
              filteredAndSortedData.map((item) => {
                const stockStatus = getStockStatus(item.current_stock);
                const riskClass = getRiskBadgeClass(item.risk_level);
                const isHighRisk = item.risk_level === 'Critical' || item.risk_level === 'High';

                return (
                  <tr key={item.sku} className={isHighRisk ? 'row-risk' : ''}>
                    <td>
                      <span className="sku-badge">{item.sku}</span>
                    </td>
                    <td>
                      <div className="product-cell">
                        <span className="product-name">{item.product_name || '-'}</span>
                      </div>
                    </td>
                    <td>{item.category || '-'}</td>
                    <td>
                      <div className="stock-cell">
                        <span className="stock-value">{item.current_stock?.toLocaleString() || 0}</span>
                        <span className={`badge badge-${stockStatus.class}`}>
                          {stockStatus.label}
                        </span>
                      </div>
                    </td>
                    <td>
                      <span className="days-value">
                        {item.days_of_stock >= 999 ? '—' : `${Math.round(item.days_of_stock)}d`}
                      </span>
                    </td>
                    <td>{item.supplier || '-'}</td>
                    <td>
                      <span className={`badge badge-${riskClass}`}>
                        {item.risk_level || 'N/A'}
                      </span>
                    </td>
                    <td>
                      <div className="action-buttons">
                        {isHighRisk && onEmail && (
                          <button
                            type="button"
                            className="btn-icon btn-icon--danger"
                            title="Email Supplier"
                            onClick={(e) => { e.stopPropagation(); onEmail(item); }}
                          >
                            <Mail size={16} />
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn-icon"
                          title="View Details"
                          onClick={(e) => { e.stopPropagation(); onView?.(item); }}
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn-icon btn-icon--primary"
                          title="AI Analysis"
                          onClick={(e) => { e.stopPropagation(); onAnalyze?.(item.sku); }}
                        >
                          <Brain size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default InventoryTable;
