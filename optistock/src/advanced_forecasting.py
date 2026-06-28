# src/advanced_forecasting.py
"""
OptiStock: Advanced Hybrid Demand Forecasting
Combines Prophet (trend/seasonality) + XGBoost (residuals) for improved accuracy.
Includes anomaly detection and explainable predictions.
"""

import pandas as pd
import numpy as np
from prophet import Prophet
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
import warnings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

# Try to import XGBoost (optional dependency)
try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost not installed - using Prophet-only forecasting")

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_percentage_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


@dataclass
class ForecastResult:
    """Structured forecast result with explainability."""
    sku: str
    forecasted_demand: int
    daily_forecast: List[Dict]
    confidence_interval: Dict
    model_metrics: Dict
    explainability: Dict
    anomalies_detected: List[Dict]


class HybridDemandForecaster:
    """
    Hybrid forecasting combining Prophet (trend/seasonality) + XGBoost (residuals).
    Provides explainable predictions with confidence intervals.
    
    Features:
    - Automatic seasonality detection (weekly, monthly, yearly)
    - Anomaly detection and handling
    - Feature engineering for XGBoost residual correction
    - Confidence intervals with uncertainty quantification
    - Explainable feature importance
    """
    
    def __init__(self, forecast_days: int = 30):
        self.forecast_days = forecast_days
        self.prophet_model = None
        self.xgb_model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.feature_importance = {}
        self.model_contributions = {}
        self.is_fitted = False
        
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer time-based and lag features for XGBoost component.
        
        Features created:
        - Calendar features (day of week, month, etc.)
        - Lag features (previous demand values)
        - Rolling statistics (moving averages, std)
        """
        df = df.copy()
        
        # Calendar features
        df['dayofweek'] = df['ds'].dt.dayofweek
        df['dayofmonth'] = df['ds'].dt.day
        df['weekofyear'] = df['ds'].dt.isocalendar().week.astype(int)
        df['month'] = df['ds'].dt.month
        df['quarter'] = df['ds'].dt.quarter
        df['is_weekend'] = (df['dayofweek'] >= 5).astype(int)
        df['is_monthend'] = (df['ds'].dt.is_month_end).astype(int)
        df['is_monthstart'] = (df['ds'].dt.is_month_start).astype(int)
        
        # Lag features (previous demand patterns)
        for lag in [1, 7, 14, 30]:
            df[f'lag_{lag}'] = df['y'].shift(lag)
        
        # Rolling statistics
        for window in [7, 14, 30]:
            df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
            df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std()
            df[f'rolling_max_{window}'] = df['y'].rolling(window=window, min_periods=1).max()
            df[f'rolling_min_{window}'] = df['y'].rolling(window=window, min_periods=1).min()
        
        # Trend indicator
        df['trend_7d'] = df['y'].diff(7)
        df['trend_30d'] = df['y'].diff(30)
        
        return df.fillna(0)
    
    def detect_anomalies(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        Detect and flag anomalies using IQR method.
        Returns cleaned data and anomaly information.
        """
        df = df.copy()
        
        Q1, Q3 = df['y'].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        lower_bound = max(0, Q1 - 1.5 * IQR)  # Demand can't be negative
        upper_bound = Q3 + 1.5 * IQR
        
        df['is_anomaly'] = ((df['y'] < lower_bound) | (df['y'] > upper_bound)).astype(int)
        df['anomaly_score'] = np.abs(df['y'] - df['y'].median()) / (df['y'].std() + 0.001)
        
        # Cap anomalies for training (don't remove, just cap)
        df['y_cleaned'] = df['y'].clip(lower_bound, upper_bound)
        
        anomaly_dates = df[df['is_anomaly'] == 1][['ds', 'y', 'anomaly_score']].to_dict('records')
        
        anomaly_info = {
            'anomaly_count': int(df['is_anomaly'].sum()),
            'anomaly_dates': [
                {
                    'date': str(a['ds'].date()) if hasattr(a['ds'], 'date') else str(a['ds']),
                    'value': float(a['y']),
                    'score': round(float(a['anomaly_score']), 2)
                }
                for a in anomaly_dates[:10]  # Limit to 10 anomalies
            ],
            'bounds': {
                'lower': round(lower_bound, 2),
                'upper': round(upper_bound, 2)
            },
            'median': round(float(df['y'].median()), 2),
            'std': round(float(df['y'].std()), 2)
        }
        
        return df, anomaly_info
    
    def detect_seasonality(self, df: pd.DataFrame) -> Dict:
        """
        Detect seasonality patterns in the data.
        """
        seasonality = {
            'weekly': False,
            'monthly': False,
            'yearly': False,
            'patterns': []
        }
        
        if len(df) < 14:
            return seasonality
        
        # Check for weekly patterns
        if len(df) >= 14:
            weekly_var = df.groupby(df['ds'].dt.dayofweek)['y'].mean().var()
            overall_var = df['y'].var()
            if weekly_var > overall_var * 0.1:
                seasonality['weekly'] = True
                seasonality['patterns'].append('Higher demand on specific weekdays detected')
        
        # Check for monthly patterns
        if len(df) >= 60:
            monthly_var = df.groupby(df['ds'].dt.day)['y'].mean().var()
            if monthly_var > overall_var * 0.1:
                seasonality['monthly'] = True
                seasonality['patterns'].append('Monthly demand patterns detected')
        
        # Check for yearly patterns
        if len(df) >= 365:
            yearly_var = df.groupby(df['ds'].dt.month)['y'].mean().var()
            if yearly_var > overall_var * 0.15:
                seasonality['yearly'] = True
                seasonality['patterns'].append('Yearly/seasonal trends detected')
        
        return seasonality
    
    def fit(self, history_df: pd.DataFrame) -> Dict:
        """
        Train hybrid model with explainability metrics.
        
        Args:
            history_df: DataFrame with 'ds' (date) and 'y' (demand) columns
            
        Returns:
            Dict with training metrics and feature importance
        """
        if len(history_df) < 7:
            raise ValueError("Need at least 7 days of history for forecasting")
        
        df = history_df.copy()
        df['ds'] = pd.to_datetime(df['ds'])
        df = df.sort_values('ds').reset_index(drop=True)
        
        # Detect anomalies
        df, anomaly_info = self.detect_anomalies(df)
        
        # Detect seasonality
        seasonality_info = self.detect_seasonality(df)
        
        # Step 1: Train Prophet on cleaned data
        prophet_df = df[['ds', 'y_cleaned']].rename(columns={'y_cleaned': 'y'})
        
        self.prophet_model = Prophet(
            yearly_seasonality=seasonality_info['yearly'] or len(df) > 180,
            weekly_seasonality=seasonality_info['weekly'] or len(df) > 14,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            interval_width=0.95
        )
        
        # Add monthly seasonality if detected
        if seasonality_info['monthly'] and len(df) > 60:
            self.prophet_model.add_seasonality(name='monthly', period=30.5, fourier_order=5)
        
        self.prophet_model.fit(prophet_df)
        
        # Get Prophet predictions on training data
        prophet_pred = self.prophet_model.predict(prophet_df)
        df['prophet_pred'] = prophet_pred['yhat'].values
        df['residual'] = df['y'] - df['prophet_pred']
        
        # Step 2: Train XGBoost on residuals (if available)
        if XGBOOST_AVAILABLE and SKLEARN_AVAILABLE and len(df) > 30:
            try:
                feature_df = self.create_features(df)
                
                feature_cols = [c for c in feature_df.columns if c not in 
                               ['ds', 'y', 'y_cleaned', 'prophet_pred', 'residual', 
                                'is_anomaly', 'anomaly_score']]
                
                X = feature_df[feature_cols].values
                y = feature_df['residual'].values
                
                X_scaled = self.scaler.fit_transform(X)
                
                self.xgb_model = XGBRegressor(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    random_state=42,
                    verbosity=0
                )
                self.xgb_model.fit(X_scaled, y)
                
                # Calculate feature importance for explainability
                self.feature_importance = dict(zip(
                    feature_cols, 
                    self.xgb_model.feature_importances_.tolist()
                ))
                
                # Sort by importance
                self.feature_importance = dict(
                    sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)
                )
                
            except Exception as e:
                logger.warning(f"XGBoost training failed: {e}, using Prophet-only")
                self.xgb_model = None
        
        # Calculate model contributions
        prophet_variance = np.var(df['prophet_pred'])
        total_variance = np.var(df['y'])
        
        prophet_contribution = min(100, max(0, (prophet_variance / total_variance * 100))) if total_variance > 0 else 100
        
        self.model_contributions = {
            'prophet_contribution': round(prophet_contribution, 2),
            'xgboost_contribution': round(100 - prophet_contribution, 2) if self.xgb_model else 0,
            'hybrid_enabled': self.xgb_model is not None,
            'anomaly_info': anomaly_info,
            'seasonality_info': seasonality_info
        }
        
        self.is_fitted = True
        
        # Calculate training metrics
        train_predictions = df['prophet_pred'].values
        if self.xgb_model:
            feature_df = self.create_features(df)
            feature_cols = [c for c in feature_df.columns if c in self.feature_importance]
            X = feature_df[feature_cols].values
            X_scaled = self.scaler.transform(X)
            train_predictions = train_predictions + self.xgb_model.predict(X_scaled)
        
        actuals = df['y'].values
        mape = np.mean(np.abs((actuals - train_predictions) / (actuals + 0.001))) * 100
        mae = np.mean(np.abs(actuals - train_predictions))
        
        return {
            'training_samples': len(df),
            'mape': round(mape, 2),
            'mae': round(mae, 2),
            'feature_importance': dict(list(self.feature_importance.items())[:10]),
            'model_contributions': self.model_contributions
        }
    
    def predict(self, sku: str = "UNKNOWN") -> ForecastResult:
        """
        Generate forecast with confidence intervals and explanations.
        
        Returns:
            ForecastResult with detailed predictions and explainability
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        # Prophet forecast
        future = self.prophet_model.make_future_dataframe(periods=self.forecast_days)
        prophet_forecast = self.prophet_model.predict(future)
        
        forecast_period = prophet_forecast.tail(self.forecast_days).copy()
        
        # Initialize predictions with Prophet baseline
        final_predictions = forecast_period['yhat'].values.copy()
        
        # Apply XGBoost correction if available
        if self.xgb_model and SKLEARN_AVAILABLE:
            try:
                forecast_period_features = forecast_period.copy()
                forecast_period_features['y'] = forecast_period_features['yhat']
                feature_df = self.create_features(forecast_period_features)
                
                feature_cols = [c for c in feature_df.columns if c in self.feature_importance]
                if feature_cols:
                    X = feature_df[feature_cols].values
                    X_scaled = self.scaler.transform(X)
                    xgb_adjustment = self.xgb_model.predict(X_scaled)
                    
                    # Combine predictions (Prophet + XGBoost residual)
                    final_predictions = final_predictions[:len(xgb_adjustment)] + xgb_adjustment
            except Exception as e:
                logger.warning(f"XGBoost prediction failed: {e}")
        
        # Build detailed daily forecast
        daily_forecast = []
        for i, (_, row) in enumerate(forecast_period.iterrows()):
            pred_value = final_predictions[i] if i < len(final_predictions) else row['yhat']
            
            daily_forecast.append({
                'date': row['ds'].strftime('%Y-%m-%d'),
                'predicted': round(max(0, pred_value), 2),
                'lower_bound': round(max(0, row['yhat_lower']), 2),
                'upper_bound': round(max(0, row['yhat_upper']), 2),
                'trend': round(row['trend'], 2),
                'weekly_effect': round(row.get('weekly', 0), 2),
                'yearly_effect': round(row.get('yearly', 0), 2)
            })
        
        # Calculate totals
        total_demand = int(sum(max(0, p['predicted']) for p in daily_forecast))
        lower_total = int(sum(p['lower_bound'] for p in daily_forecast))
        upper_total = int(sum(p['upper_bound'] for p in daily_forecast))
        
        # Calculate confidence level based on data quality
        confidence_score = 0.85
        if self.model_contributions.get('anomaly_info', {}).get('anomaly_count', 0) > 5:
            confidence_score -= 0.1
        if self.xgb_model:
            confidence_score += 0.05
        confidence_score = round(min(0.95, max(0.5, confidence_score)), 2)
        
        # Build explainability section
        top_features = dict(list(self.feature_importance.items())[:5]) if self.feature_importance else {}
        
        explainability = {
            'top_features': top_features,
            'model_contributions': self.model_contributions,
            'seasonality_detected': self.model_contributions.get('seasonality_info', {}),
            'confidence_score': confidence_score,
            'forecast_method': 'Hybrid (Prophet + XGBoost)' if self.xgb_model else 'Prophet',
            'interpretation': self._generate_interpretation(daily_forecast, total_demand)
        }
        
        return ForecastResult(
            sku=sku,
            forecasted_demand=total_demand,
            daily_forecast=daily_forecast,
            confidence_interval={
                'lower': lower_total,
                'upper': upper_total,
                'confidence_level': 0.95
            },
            model_metrics={
                'confidence_score': confidence_score,
                'hybrid_enabled': self.xgb_model is not None,
                'training_samples': self.model_contributions.get('training_samples', 0)
            },
            explainability=explainability,
            anomalies_detected=self.model_contributions.get('anomaly_info', {}).get('anomaly_dates', [])
        )
    
    def _generate_interpretation(self, daily_forecast: List[Dict], total_demand: int) -> str:
        """Generate human-readable interpretation of the forecast."""
        
        # Analyze trend
        first_week_avg = np.mean([d['predicted'] for d in daily_forecast[:7]])
        last_week_avg = np.mean([d['predicted'] for d in daily_forecast[-7:]])
        
        trend = "stable"
        if last_week_avg > first_week_avg * 1.1:
            trend = "increasing"
        elif last_week_avg < first_week_avg * 0.9:
            trend = "decreasing"
        
        # Find peak days
        peak_day = max(daily_forecast, key=lambda x: x['predicted'])
        low_day = min(daily_forecast, key=lambda x: x['predicted'])
        
        interpretation = f"Forecasted {self.forecast_days}-day demand is {total_demand} units with {trend} trend. "
        interpretation += f"Peak expected on {peak_day['date']} ({round(peak_day['predicted'])} units). "
        interpretation += f"Lowest on {low_day['date']} ({round(low_day['predicted'])} units)."
        
        return interpretation


def run_hybrid_forecast(
    history_df: pd.DataFrame, 
    sku: str, 
    forecast_days: int = 30
) -> Dict:
    """
    Convenience function to run hybrid forecast.
    
    Args:
        history_df: DataFrame with 'ds' and 'y' columns
        sku: Product SKU identifier
        forecast_days: Number of days to forecast
        
    Returns:
        Dict with forecast results
    """
    forecaster = HybridDemandForecaster(forecast_days=forecast_days)
    
    try:
        training_info = forecaster.fit(history_df)
        result = forecaster.predict(sku)
        
        return {
            'success': True,
            'sku': result.sku,
            'forecasted_demand_30_days': result.forecasted_demand,
            'daily_forecast': result.daily_forecast,
            'confidence_interval': result.confidence_interval,
            'model_metrics': result.model_metrics,
            'explainability': result.explainability,
            'anomalies_detected': result.anomalies_detected,
            'training_info': training_info
        }
    except Exception as e:
        logger.error(f"Hybrid forecast failed for {sku}: {e}")
        return {
            'success': False,
            'sku': sku,
            'error': str(e)
        }
