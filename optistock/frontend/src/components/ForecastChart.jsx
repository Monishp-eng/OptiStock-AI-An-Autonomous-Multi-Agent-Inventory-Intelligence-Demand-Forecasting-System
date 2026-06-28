import React from 'react';
import { 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Area,
  AreaChart
} from 'recharts';
import './ForecastChart.css';

function ForecastChart({ data, title = "30-Day Demand Forecast" }) {
  if (!data || data.length === 0) {
    return (
      <div className="forecast-chart-empty">
        <p>No forecast data available</p>
      </div>
    );
  }

  // Transform data for the chart
  const chartData = data.map(item => ({
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    predicted: Math.max(0, item.predicted),
    lower: Math.max(0, item.lower_bound),
    upper: Math.max(0, item.upper_bound),
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="chart-tooltip">
          <p className="tooltip-label">{label}</p>
          <p className="tooltip-value">
            <span className="tooltip-dot predicted"></span>
            Predicted: {payload[0]?.value?.toFixed(0)} units
          </p>
          {payload[1] && (
            <p className="tooltip-range">
              Range: {payload[1]?.payload?.lower?.toFixed(0)} - {payload[1]?.payload?.upper?.toFixed(0)}
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="forecast-chart">
      <h3 className="chart-title">{title}</h3>
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorPredicted" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorRange" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2}/>
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis 
              dataKey="date" 
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              tickLine={{ stroke: '#334155' }}
            />
            <YAxis 
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              tickLine={{ stroke: '#334155' }}
              tickFormatter={(value) => `${value}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="upper"
              stroke="transparent"
              fill="url(#colorRange)"
              fillOpacity={1}
            />
            <Area
              type="monotone"
              dataKey="predicted"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#colorPredicted)"
              fillOpacity={1}
            />
            <Area
              type="monotone"
              dataKey="lower"
              stroke="#8b5cf6"
              strokeWidth={1}
              strokeDasharray="5 5"
              fill="transparent"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend">
        <div className="legend-item">
          <span className="legend-line predicted"></span>
          <span>Predicted Demand</span>
        </div>
        <div className="legend-item">
          <span className="legend-line range"></span>
          <span>Confidence Range</span>
        </div>
      </div>
    </div>
  );
}

export default ForecastChart;
