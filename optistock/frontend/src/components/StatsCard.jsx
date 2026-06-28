import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import './StatsCard.css';

function StatsCard({ title, value, subtitle, icon, trend, trendValue, color = 'blue', variant }) {
  const getTrendIcon = () => {
    if (trend === 'up') return <TrendingUp size={14} />;
    if (trend === 'down') return <TrendingDown size={14} />;
    return <Minus size={14} />;
  };

  // Use variant if provided, otherwise fall back to color
  const cardColor = variant || color;

  // Handle icon as either a React element or component
  const renderIcon = () => {
    if (!icon) return null;
    // If icon is already a React element (JSX), render it directly
    if (React.isValidElement(icon)) return icon;
    // If icon is a component, instantiate it
    const IconComponent = icon;
    return <IconComponent size={24} />;
  };

  return (
    <div className={`stats-card stats-card--${cardColor}`}>
      <div className="stats-card-header">
        <div className="stats-card-icon">
          {renderIcon()}
        </div>
        {trendValue && (
          <div className={`stats-card-trend trend--${trend || 'neutral'}`}>
            {getTrendIcon()}
            <span>{trendValue}</span>
          </div>
        )}
      </div>
      <div className="stats-card-body">
        <h3 className="stats-card-value">{value}</h3>
        <p className="stats-card-title">{title}</p>
        {subtitle && <p className="stats-card-subtitle">{subtitle}</p>}
      </div>
    </div>
  );
}

export default StatsCard;
