# src/data_handler.py

import pandas as pd

def load_inventory() -> pd.DataFrame:
    """Loads the inventory data from the CSV file."""
    return pd.read_csv('data/inventory.csv')

def load_sales_history() -> pd.DataFrame:
    """Loads the sales history data from the CSV file."""
    df = pd.read_csv('data/sales_history.csv')
    df['ds'] = pd.to_datetime(df['ds'])
    return df
