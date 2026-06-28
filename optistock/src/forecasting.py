# src/forecasting.py
# Demand forecasting using statsmodels ExponentialSmoothing (Holt-Winters).
# Prophet dependency removed entirely.

import pandas as pd
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def generate_forecast(history_df: pd.DataFrame, days_to_forecast: int = 30):
    """
    Generates a demand forecast using Holt-Winters ExponentialSmoothing.

    Args:
        history_df: DataFrame with 'ds' (date) and 'y' (quantity) columns.
        days_to_forecast: Number of days into the future to forecast.

    Returns:
        (forecast_dict, plot_data_list) where forecast_dict has keys:
          - forecasted_demand_30_days (int)
          - plot_data (list of {date, value})
        and plot_data_list is an alias for forecast_dict['plot_data'].

    Fallback: If < 14 training observations exist, uses a rolling 7-day average.
    """
    if 'ds' not in history_df.columns or 'y' not in history_df.columns:
        raise ValueError("Input DataFrame must have 'ds' and 'y' columns.")

    series = (
        history_df
        .dropna(subset=['ds', 'y'])
        .sort_values('ds')
        .set_index('ds')['y']
        .astype(float)
    )

    MIN_OBS = 14
    last_date = series.index[-1] if len(series) else pd.Timestamp.today()
    future_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=days_to_forecast,
        freq='D'
    )

    if len(series) >= MIN_OBS:
        try:
            # Weekly seasonality (seasonal_periods=7) when we have enough data
            seasonal = 'add' if len(series) >= 14 else None
            sp = 7 if seasonal else None

            model = ExponentialSmoothing(
                series.values,
                trend='add',
                seasonal=seasonal,
                seasonal_periods=sp,
                initialization_method='estimated',
            ).fit(optimized=True, remove_bias=True)

            future_values = model.forecast(days_to_forecast)
            # Clip negatives (demand can't be < 0)
            future_values = np.clip(future_values, 0, None)

        except (ValueError, np.linalg.LinAlgError):
            # Fall back to rolling average if optimisation fails
            future_values = _rolling_average_forecast(series, days_to_forecast)
    else:
        future_values = _rolling_average_forecast(series, days_to_forecast)

    total_demand = max(int(round(float(np.sum(future_values)))), 0)

    plot_data = [
        {"date": d.strftime('%Y-%m-%d'), "value": max(0.0, round(float(v), 2))}
        for d, v in zip(future_dates, future_values)
    ]

    forecast_dict = {
        "forecasted_demand_30_days": total_demand,
        "plot_data": plot_data,
    }
    return forecast_dict, plot_data


def _rolling_average_forecast(series: pd.Series, days: int) -> np.ndarray:
    """Rolling 7-day average fallback for short series."""
    window = min(7, len(series))
    avg = float(series.iloc[-window:].mean()) if window > 0 else 0.0
    return np.full(days, max(avg, 0.0))


def get_forecasted_demand(forecast_dict: dict, days: int) -> int:
    """
    Extracts total forecasted demand for `days` from a forecast_dict.
    Accepts the dict returned by generate_forecast().
    """
    plot_data = forecast_dict.get('plot_data', [])
    total = sum(entry['value'] for entry in plot_data[:days])
    return max(int(round(total)), 0)
