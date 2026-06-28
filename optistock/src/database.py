"""
database.py — SQLite foundation for OptiStock
Handles: table creation, CSV migration, connection helper
"""
import sqlite3
import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DB_PATH = str(BASE_DIR / "data" / "optistock.db")
CSV_PATH = str(BASE_DIR / "data" / "supply_chain_data.csv")


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db():
    """FastAPI dependency — yields a connection and closes it after the request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inventory_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sku             TEXT    UNIQUE NOT NULL,
                product_name    TEXT    NOT NULL DEFAULT '',
                category        TEXT    DEFAULT '',
                current_stock   INTEGER DEFAULT 0,
                cost_per_unit   REAL    DEFAULT 0,
                selling_price   REAL    DEFAULT 0,
                supplier        TEXT    DEFAULT '',
                defect_rate     REAL    DEFAULT 0.01,
                lead_time_days  INTEGER DEFAULT 7,
                created_at      TEXT,
                updated_at      TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_sales (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                sku        TEXT NOT NULL,
                quantity   INTEGER NOT NULL DEFAULT 0,
                sale_date  TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (sku) REFERENCES inventory_items(sku)
            );

            CREATE INDEX IF NOT EXISTS idx_daily_sales_sku ON daily_sales(sku);
            CREATE INDEX IF NOT EXISTS idx_daily_sales_date ON daily_sales(sale_date);

            CREATE TABLE IF NOT EXISTS suppliers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                contact_person   TEXT DEFAULT '',
                phone            TEXT DEFAULT '',
                whatsapp_number  TEXT DEFAULT '',
                email            TEXT DEFAULT '',
                address          TEXT DEFAULT '',
                notes            TEXT DEFAULT '',
                created_at       TEXT
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                sku                  TEXT,
                supplier_id          INTEGER,
                quantity             INTEGER NOT NULL DEFAULT 0,
                status               TEXT    DEFAULT 'pending',
                unit_cost            REAL    DEFAULT 0,
                total_cost           REAL    DEFAULT 0,
                ordered_at           TEXT,
                expected_delivery_at TEXT,
                notes                TEXT DEFAULT '',
                FOREIGN KEY (sku) REFERENCES inventory_items(sku),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id            TEXT PRIMARY KEY,
                timestamp     TEXT NOT NULL,
                event_type    TEXT NOT NULL,
                source_agent  TEXT NOT NULL,
                sku           TEXT,
                product_name  TEXT,
                title         TEXT NOT NULL,
                message       TEXT NOT NULL,
                priority      TEXT NOT NULL,
                whatsapp_link TEXT,
                is_read       INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        logger.info("✅ Database tables initialized")
    finally:
        conn.close()


def migrate_csv_to_sqlite():
    """
    One-time migration of supply_chain_data.csv into SQLite.
    Idempotent — skips entirely if inventory_items already has rows.
    """
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
        if count > 0:
            logger.info(f"⏭️  Database already has {count} products — skipping CSV migration")
            return

        if not os.path.exists(CSV_PATH):
            logger.warning(f"⚠️  CSV not found at {CSV_PATH} — starting with empty database")
            return

        import pandas as pd
        df = pd.read_csv(CSV_PATH)
        logger.info(f"📂 Migrating CSV: {len(df)} rows, columns: {list(df.columns)}")

        # Normalise column names to lowercase
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        # Map CSV columns → DB columns (handles varying CSV schemas)
        col_map = {
            'sku': 'sku',
            'product_name': 'product_name',
            'category': 'category',
            'current_stock': 'current_stock',
            'cost_per_unit': 'cost_per_unit',
            'supplier': 'supplier',
            'defect_rate': 'defect_rate',
            'lead_time_days': 'lead_time_days',
            'sales_date': 'sale_date',
            'quantity_sold': 'quantity',
        }
        # Rename to normalised names where they exist
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        now = datetime.utcnow().isoformat()

        # --- Migrate inventory_items (one row per unique SKU) ---
        static_cols = ['sku', 'product_name', 'category', 'current_stock',
                       'cost_per_unit', 'supplier', 'defect_rate', 'lead_time_days']
        available = [c for c in static_cols if c in df.columns]
        unique_skus = df.drop_duplicates(subset=['sku'])[available].copy()

        item_count = 0
        for _, row in unique_skus.iterrows():
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO inventory_items
                        (sku, product_name, category, current_stock, cost_per_unit,
                         selling_price, supplier, defect_rate, lead_time_days,
                         created_at, updated_at)
                    VALUES (?,?,?,?,?,0,?,?,?,?,?)
                """, (
                    str(row.get('sku', '')).upper(),
                    str(row.get('product_name', '')),
                    str(row.get('category', '')),
                    int(row.get('current_stock', 0) or 0),
                    float(row.get('cost_per_unit', 0) or 0),
                    str(row.get('supplier', '')),
                    float(row.get('defect_rate', 0.01) or 0.01),
                    int(row.get('lead_time_days', 7) or 7),
                    now, now,
                ))
                item_count += 1
            except Exception as e:
                logger.warning(f"Skipping SKU row: {e}")

        # --- Migrate daily_sales ---
        sales_count = 0
        if 'sale_date' in df.columns and 'quantity' in df.columns:
            sales_df = df[['sku', 'quantity', 'sale_date']].dropna(
                subset=['sale_date', 'quantity'])
            for _, row in sales_df.iterrows():
                try:
                    conn.execute("""
                        INSERT INTO daily_sales (sku, quantity, sale_date, created_at)
                        VALUES (?,?,?,?)
                    """, (
                        str(row['sku']).upper(),
                        int(row['quantity'] or 0),
                        str(row['sale_date'])[:10],
                        now,
                    ))
                    sales_count += 1
                except Exception as e:
                    logger.warning(f"Skipping sale row: {e}")

        conn.commit()
        logger.info(f"✅ Migration complete — {item_count} products, {sales_count} sales records")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()
