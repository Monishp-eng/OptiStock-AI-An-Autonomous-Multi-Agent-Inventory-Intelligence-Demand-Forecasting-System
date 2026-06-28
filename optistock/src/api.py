# -*- coding: utf-8 -*-
"""
OptiStock: FastAPI Backend
Production-ready REST API for the OptiStock Procurement Agent.
Designed to be consumed by a React frontend.
"""

# --- Core Imports ---
import os
import logging
import json
import re
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
from datetime import datetime
import threading
from pathlib import Path
from contextlib import asynccontextmanager

# --- Load .env file BEFORE anything else ---
def load_dotenv_file():
    """Load environment variables from .env file manually (no dependencies)."""
    # Find .env file relative to this file's location
    current_dir = Path(__file__).parent.parent  # Go up from src/ to project root
    env_path = current_dir / ".env"
    
    if not env_path.exists():
        return False
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse key=value
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                # .env file always overrides system environment variables
                if key:
                    os.environ[key] = value
    return True

# Load .env at import time
_env_loaded = load_dotenv_file()

# --- Library Imports ---
import pandas as pd
from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Logging Configuration (must be before other imports that use logger) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Google Cloud & Vertex AI Imports ---
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    VERTEXAI_AVAILABLE = True
except ImportError:
    VERTEXAI_AVAILABLE = False

# --- Google Generative AI (Gemini) Import ---
try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GENAI_AVAILABLE = True
        logger.info("✅ Gemini AI configured successfully")
    else:
        GENAI_AVAILABLE = False
        logger.warning("⚠️ GOOGLE_API_KEY not found - AI features disabled")
except ImportError:
    GENAI_AVAILABLE = False
    GEMINI_API_KEY = None
    logger.warning("⚠️ google-generativeai not installed - AI features disabled")

# =============================================================================
# PYDANTIC MODELS - Strict typing for React frontend consumption
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = "healthy"
    timestamp: str
    version: str = "1.0.0"


class InventoryItem(BaseModel):
    """Model for inventory item - used for both reading and creating."""
    sku: str = Field(..., description="Unique product SKU identifier", examples=["SKU-001"])
    product_name: str = Field(..., description="Product display name", examples=["Smartwatch Model X"])
    category: str = Field(..., description="Product category", examples=["Electronics"])
    current_stock: int = Field(..., ge=0, description="Current inventory units")
    cost_per_unit: float = Field(..., gt=0, description="Cost per unit in USD")
    supplier: str = Field(..., description="Supplier name")
    defect_rate: float = Field(..., ge=0, le=1, description="Defect rate (0-1)")
    lead_time_days: int = Field(..., ge=0, description="Supplier lead time in days")


class InventoryItemCreate(BaseModel):
    """Model for creating a new inventory item (without sales data)."""
    sku: str = Field(..., description="Unique product SKU identifier")
    product_name: str = Field(..., description="Product display name")
    category: str = Field(..., description="Product category")
    current_stock: int = Field(..., ge=0, description="Current inventory units")
    cost_per_unit: float = Field(..., gt=0, description="Cost per unit in USD")
    supplier: str = Field(..., description="Supplier name")
    defect_rate: float = Field(0.01, ge=0, le=1, description="Defect rate (0-1)")
    lead_time_days: int = Field(7, ge=0, description="Supplier lead time in days")


class ForecastDataPoint(BaseModel):
    """Single data point in forecast results."""
    date: str
    predicted: float
    lower_bound: float
    upper_bound: float


class ForecastResult(BaseModel):
    """Demand forecast result for an SKU."""
    sku: str
    forecasted_demand_30_days: int
    plot_data: List[ForecastDataPoint]


class RiskAssessment(BaseModel):
    """Supplier risk assessment result."""
    risk_score: float
    risk_level: str  # "High", "Medium", "Low"


class EmailDraft(BaseModel):
    """Email draft structure for procurement negotiations."""
    subject: str
    body: str


class AgentResponse(BaseModel):
    """
    Complete agent analysis response.
    This is the main response model consumed by the React frontend.
    """
    sku: str
    product_name: str
    decision: str = Field(..., description="Either 'Restock' or 'Hold'")
    confidence_score: float = Field(..., ge=0, le=1, description="Agent confidence (0-1)")
    reasoning: str
    current_stock: int
    forecasted_demand: int
    risk_assessment: RiskAssessment
    email_draft: Optional[EmailDraft] = None
    plot_data: List[ForecastDataPoint] = []


class InventoryListResponse(BaseModel):
    """Response model for inventory list endpoint."""
    items: List[Dict[str, Any]]
    total_count: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: str


class EmailSendRequest(BaseModel):
    """Request model for sending an email."""
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content")
    sku: Optional[str] = Field(None, description="Related SKU for tracking")


class EmailSendResponse(BaseModel):
    """Response model after sending an email."""
    success: bool
    message: str
    email_id: Optional[str] = None
    sent_at: Optional[str] = None
    from_email: Optional[str] = None
    to_email: Optional[str] = None


class EmailConfigResponse(BaseModel):
    """Response model for email configuration status."""
    configured: bool
    email_address: Optional[str] = None
    smtp_host: str
    smtp_port: int


# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise SQLite DB and migrate CSV data."""
    from src.database import init_db, migrate_csv_to_sqlite
    init_db()
    migrate_csv_to_sqlite()
    logger.info("✅ SQLite database ready")
    yield

app = FastAPI(
    title="OptiStock API",
    description="REST API for the OptiStock Autonomous Procurement Agent",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- Include Enhanced API Router ---
try:
    from src.enhanced_api import router as enhanced_router
    app.include_router(enhanced_router)
    logger.info("✅ Enhanced API v2 endpoints loaded")
except ImportError as e:
    logger.warning(f"⚠️ Enhanced API not available: {e}")

# --- Include new feature routers ---
from src.routers.auth_router import router as auth_router
from src.routers.sales_router import router as sales_router
from src.routers.suppliers_router import router as suppliers_router
from src.routers.orders_router import router as orders_router
from src.routers.profit_router import router as profit_router
from src.routers.export_router import router as export_router

app.include_router(auth_router)
app.include_router(sales_router)
app.include_router(suppliers_router)
app.include_router(orders_router)
app.include_router(profit_router)
app.include_router(export_router)

# --- Include AI Agents router ---
try:
    from src.routers.agents_router import router as agents_router
    app.include_router(agents_router)
    logger.info("✅ AI Agents router loaded")
except ImportError as e:
    logger.warning(f"⚠️ AI Agents router not available: {e}")

logger.info("✅ Feature routers loaded (auth, sales, suppliers, orders, profit, export, agents)")

# --- Auth dependency ---
from src.auth import get_current_user

# --- CORS Middleware Configuration ---
# Allow all origins for development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://optistock-frontend-455361778474.asia-south1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- File lock for thread-safe CSV writes ---
csv_write_lock = threading.Lock()

# --- Data file path (use absolute path relative to this file's location) ---
# __file__ is src/api.py, so we go up one level to reach the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE_PATH = os.path.join(BASE_DIR, "data", "supply_chain_data.csv")

# Compatibility stub — kept so legacy upload endpoint doesn't raise NameError
UPLOADED_DATA_CACHE: Dict[str, pd.DataFrame] = {}
DATA_CACHE_KEY = "current_data"

# Log the path at startup for debugging
logger.info(f"Data file path: {DATA_FILE_PATH}")

# --- Email Configuration (Gmail SMTP) ---
# Set these environment variables:
#   SMTP_EMAIL=your-email@gmail.com
#   SMTP_PASSWORD=your-app-password (NOT your Gmail password)
#   SMTP_RECIPIENT=default-recipient@example.com (optional)
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_RECIPIENT = os.environ.get("SMTP_RECIPIENT", "")  # Default recipient for demos
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

EMAIL_CONFIGURED = bool(SMTP_EMAIL and SMTP_PASSWORD)
if EMAIL_CONFIGURED:
    logger.info(f"✅ Email configured with: {SMTP_EMAIL}")
else:
    logger.warning("⚠️ Email not configured. Set SMTP_EMAIL and SMTP_PASSWORD environment variables.")


def send_email_smtp(to_email: str, subject: str, body: str, is_html: bool = False) -> Dict[str, Any]:
    """
    Send email using Gmail SMTP.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Email body (plain text or HTML)
        is_html: Whether the body is HTML
    
    Returns:
        Dict with success status and message
    """
    if not EMAIL_CONFIGURED:
        return {
            "success": False,
            "message": "Email not configured. Set SMTP_EMAIL and SMTP_PASSWORD environment variables.",
            "simulated": True
        }
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_EMAIL
        msg["To"] = to_email
        
        # Attach body
        if is_html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))
        
        # Connect and send — SSL on port 465, STARTTLS on all others
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        
        logger.info(f"📧 Email sent successfully to {to_email}")
        return {
            "success": True,
            "message": f"Email sent to {to_email}",
            "from": SMTP_EMAIL,
            "to": to_email,
            "subject": subject
        }
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        return {
            "success": False,
            "message": "Authentication failed. Check SMTP_EMAIL and SMTP_PASSWORD. For Gmail, use an App Password.",
            "error": str(e)
        }
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return {
            "success": False,
            "message": f"SMTP error: {str(e)}",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        return {
            "success": False,
            "message": f"Failed to send email: {str(e)}",
            "error": str(e)
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_supply_chain_data() -> pd.DataFrame:
    """Loads inventory + sales data from SQLite into a DataFrame with CSV-compatible column names."""
    import sqlite3
    from src.database import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT
                i.sku         AS SKU,
                i.product_name AS Product_Name,
                i.category     AS Category,
                i.current_stock AS Current_Stock,
                i.cost_per_unit AS Cost_Per_Unit,
                i.supplier     AS Supplier,
                i.defect_rate  AS Defect_Rate,
                i.lead_time_days AS Lead_Time_Days,
                s.sale_date    AS Sales_Date,
                s.quantity     AS Quantity_Sold
            FROM inventory_items i
            LEFT JOIN daily_sales s ON i.sku = s.sku
            ORDER BY i.sku, s.sale_date
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=[
            'SKU', 'Product_Name', 'Category', 'Current_Stock',
            'Cost_Per_Unit', 'Supplier', 'Defect_Rate',
            'Lead_Time_Days', 'Sales_Date', 'Quantity_Sold'
        ])

    df = pd.DataFrame([dict(r) for r in rows])
    df['SKU'] = df['SKU'].astype(str)
    df['Sales_Date'] = pd.to_datetime(df['Sales_Date'], errors='coerce')
    df = df.dropna(subset=['Sales_Date'])
    df['Current_Stock'] = df['Current_Stock'].fillna(0)
    df['Cost_Per_Unit'] = df['Cost_Per_Unit'].fillna(0)
    df['Defect_Rate'] = df['Defect_Rate'].fillna(0.01)
    df['Lead_Time_Days'] = df['Lead_Time_Days'].fillna(7)
    df['Quantity_Sold'] = df['Quantity_Sold'].fillna(0)
    logger.info(f"Loaded {len(df)} records from SQLite, {df['SKU'].nunique()} unique SKUs")
    return df


def get_inventory_for_sku(df: pd.DataFrame, sku: str) -> Dict[str, Any]:
    """Extracts inventory information for a specific SKU."""
    data = df[df['SKU'].str.lower() == sku.lower()]
    if data.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with SKU '{sku}' not found."
        )
    rec = data.iloc[0]
    return {
        "sku": str(rec['SKU']),
        "product_name": str(rec['Product_Name']),
        "category": str(rec['Category']),
        "current_stock": int(rec['Current_Stock']),
        "cost_per_unit": float(rec['Cost_Per_Unit']),
        "supplier": str(rec['Supplier']),
        "defect_rate": float(rec['Defect_Rate']),
        "lead_time_days": int(rec['Lead_Time_Days'])
    }


def run_demand_forecast(df: pd.DataFrame, sku: str) -> Dict[str, Any]:
    """Runs ExponentialSmoothing demand forecast for an SKU."""
    from src.forecasting import generate_forecast as _generate_forecast

    history = df[df['SKU'] == sku][['Sales_Date', 'Quantity_Sold']].copy()

    if history.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sales history found for SKU '{sku}'."
        )

    history = history.rename(columns={'Sales_Date': 'ds', 'Quantity_Sold': 'y'})
    forecast_dict, _ = _generate_forecast(history, days_to_forecast=30)

    # Convert {date, value} → ForecastDataPoint shape {date, predicted, lower_bound, upper_bound}
    plot_data = []
    for entry in forecast_dict['plot_data']:
        v = entry['value']
        spread = max(v * 0.2, 1.0)
        plot_data.append({
            "date": entry['date'],
            "predicted": round(v, 2),
            "lower_bound": round(max(v - spread, 0.0), 2),
            "upper_bound": round(v + spread, 2),
        })

    return {
        "sku": sku,
        "forecasted_demand_30_days": forecast_dict['forecasted_demand_30_days'],
        "plot_data": plot_data,
    }


def calculate_supply_risk(defect_rate: float, lead_time_days: int) -> Dict[str, Any]:
    """Computes supplier risk score."""
    risk_score = (defect_rate * 100) * 2 + (lead_time_days / 7)
    
    if risk_score > 10:
        level = "High"
    elif risk_score > 5:
        level = "Medium"
    else:
        level = "Low"
    
    return {
        "risk_score": round(risk_score, 2),
        "risk_level": level
    }


def generate_email_with_gemini(
    product_name: str,
    supplier_name: str,
    required_units: int,
    reason: str
) -> Optional[Dict[str, str]]:
    """Generates procurement email using Gemini."""
    if not VERTEXAI_AVAILABLE:
        # Return mock email if Vertex AI not available
        return {
            "subject": f"Procurement Request: {product_name}",
            "body": f"""Dear {supplier_name} Team,

We are writing to inquire about placing an order for {required_units} units of {product_name}.

Reason for order: {reason}

Could you please provide:
1. Current pricing for this quantity
2. Expected lead time
3. Any bulk order discounts available

We look forward to your prompt response.

Best regards,
OptiStock Procurement Team"""
        }
    
    try:
        PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not PROJECT_ID:
            logger.warning("GOOGLE_CLOUD_PROJECT not set, using mock email")
            return None
        
        vertexai.init(project=PROJECT_ID, location="us-central1")
        model = GenerativeModel("gemini-1.5-pro-001")
        
        prompt = f"""Draft a professional procurement email.
**Product:** {product_name}
**Supplier:** {supplier_name}
**Reason:** {reason}
**Units Required:** {required_units}
**Instructions:** Be polite. If it's a bulk order (>100 units), ask for a 10% discount. 
Always request a quote and lead time. Format as: Subject: [Subject]\n\n[Body]"""
        
        response = model.generate_content(prompt)
        email_text = response.text
        
        # Parse subject and body
        if "Subject:" in email_text:
            subject = email_text.split("Subject:")[1].split("\n\n")[0].strip()
            body = email_text.split("\n\n", 1)[1].strip() if "\n\n" in email_text else email_text
        else:
            subject = f"Procurement Request: {product_name}"
            body = email_text
        
        return {"subject": subject, "body": body}
    except Exception as e:
        logger.error(f"Gemini email generation failed: {e}")
        return None


# =============================================================================
# FIRESTORE & PUB/SUB INTEGRATION (Cloud Deployment)
# =============================================================================

# Import cloud modules (optional - won't fail locally)
try:
    from src.firestore_db import (
        FIRESTORE_AVAILABLE,
        save_inventory_data,
        get_inventory_data as get_firestore_inventory,
        save_forecast,
        save_alert,
        log_agent_run,
        get_agent_run_history,
        health_check as firestore_health_check
    )
except ImportError:
    FIRESTORE_AVAILABLE = False
    logger.info("Firestore module not loaded - running in local mode")

try:
    from src.pubsub_handler import (
        parse_pubsub_message,
        validate_scheduler_request,
        create_run_context
    )
    PUBSUB_HANDLER_AVAILABLE = True
except ImportError:
    PUBSUB_HANDLER_AVAILABLE = False
    logger.info("Pub/Sub handler not loaded")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns the API status and current timestamp.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@app.get("/api/data-status", tags=["System"])
async def get_data_status():
    """
    Check the current data status - shows if data is from upload or default.
    """
    has_uploaded_data = False  # SQLite is now the persistent store

    try:
        df = load_supply_chain_data()
        unique_skus = df['SKU'].unique().tolist()
        return {
            "source": "sqlite",
            "total_records": len(df),
            "unique_products": len(unique_skus),
            "products": unique_skus,
            "message": "Data loaded from SQLite database"
        }
    except Exception as e:
        return {
            "source": "none",
            "total_records": 0,
            "unique_products": 0,
            "products": [],
            "message": f"No data available: {str(e)}"
        }


@app.delete("/api/data-clear", tags=["System"])
async def clear_uploaded_data():
    """
    No-op endpoint kept for API compatibility. Data now persists in SQLite.
    """
    return {"success": True, "message": "Data is stored in SQLite. Use inventory endpoints to manage items."}


@app.get("/api/inventory", response_model=InventoryListResponse, tags=["Inventory"])
async def get_all_inventory(current_user: dict = Depends(get_current_user)):
    """
    Get all inventory items with risk levels and days-of-stock.
    daysOfStock = CurrentStock / AvgDailySales
    """
    df = load_supply_chain_data()

    # Get unique SKUs with their latest info, plus calculated fields
    inventory_items = []
    for sku in df['SKU'].unique():
        sku_rows = df[df['SKU'] == sku]
        rec = sku_rows.iloc[0]

        # Calculate average daily sales from sales history
        sales = sku_rows[['Sales_Date', 'Quantity_Sold']].copy()
        sales['Sales_Date'] = pd.to_datetime(sales['Sales_Date'])
        total_sold = float(sales['Quantity_Sold'].sum())
        date_range = (sales['Sales_Date'].max() - sales['Sales_Date'].min()).days
        num_days = max(date_range, 1)
        avg_daily_sales = total_sold / num_days if num_days > 0 else 0

        # daysOfStock = CurrentStock / AvgDailySales
        current_stock = int(rec['Current_Stock'])
        days_of_stock = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else 999

        # Risk level based on days of stock vs lead time
        lead_time = int(rec['Lead_Time_Days'])
        if avg_daily_sales <= 0:
            risk_level = "Low"
        elif days_of_stock < lead_time:
            risk_level = "Critical"
        elif days_of_stock < lead_time * 2:
            risk_level = "High"
        elif days_of_stock < 30:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        inventory_items.append({
            "sku": str(rec['SKU']),
            "product_name": str(rec['Product_Name']),
            "category": str(rec['Category']),
            "current_stock": current_stock,
            "cost_per_unit": float(rec['Cost_Per_Unit']),
            "supplier": str(rec['Supplier']),
            "defect_rate": float(rec['Defect_Rate']),
            "lead_time_days": lead_time,
            "avg_daily_sales": round(avg_daily_sales, 2),
            "days_of_stock": round(days_of_stock, 1),
            "risk_level": risk_level,
        })

    return InventoryListResponse(
        items=inventory_items,
        total_count=len(inventory_items)
    )


@app.get("/api/inventory/{sku}", tags=["Inventory"])
async def get_inventory_by_sku(sku: str, current_user: dict = Depends(get_current_user)):
    """
    Get inventory details for a specific SKU.
    """
    df = load_supply_chain_data()
    return get_inventory_for_sku(df, sku)


@app.post("/api/inventory", status_code=status.HTTP_201_CREATED, tags=["Inventory"])
async def create_inventory_item(item: InventoryItemCreate, current_user: dict = Depends(get_current_user)):
    """
    Add a new inventory item.
    Appends the item to the CSV file with an initial sales record.
    """
    df = load_supply_chain_data()
    
    # Check if SKU already exists (convert to string for comparison)
    existing_skus = df['SKU'].astype(str).str.upper().tolist()
    if item.sku.upper() in existing_skus:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU '{item.sku}' already exists."
        )
    
    # Create new row with current date as sales date and 0 quantity sold
    new_row = {
        'SKU': item.sku.upper(),
        'Product_Name': item.product_name,
        'Category': item.category,
        'Current_Stock': item.current_stock,
        'Cost_Per_Unit': item.cost_per_unit,
        'Supplier': item.supplier,
        'Defect_Rate': item.defect_rate,
        'Lead_Time_Days': item.lead_time_days,
    }
    
    # Save to SQLite
    try:
        import sqlite3
        from src.database import DB_PATH
        from datetime import datetime as _dt
        _now = _dt.utcnow().isoformat()
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute("""
            INSERT INTO inventory_items
                (sku, product_name, category, current_stock, cost_per_unit,
                 selling_price, supplier, defect_rate, lead_time_days, created_at, updated_at)
            VALUES (?,?,?,?,?,0,?,?,?,?,?)
        """, (item.sku.upper(), item.product_name, item.category,
              item.current_stock, item.cost_per_unit,
              item.supplier, item.defect_rate, item.lead_time_days, _now, _now))
        _conn.commit()
        _conn.close()
        logger.info(f"New inventory item added to SQLite: {item.sku}")
    except Exception as e:
        logger.error(f"Failed to save to SQLite: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save inventory item: {str(e)}"
        )
    
    return {
        "message": f"Inventory item '{item.sku}' created successfully.",
        "item": new_row
    }


@app.get("/api/forecast/{sku}", response_model=ForecastResult, tags=["Forecasting"])
async def get_demand_forecast(sku: str, current_user: dict = Depends(get_current_user)):
    """
    Get 30-day demand forecast for a specific SKU.
    Uses Prophet ML model for time-series forecasting.
    """
    df = load_supply_chain_data()
    return run_demand_forecast(df, sku)


@app.post("/api/agent/analyze/{sku}", response_model=AgentResponse, tags=["Agent"])
async def analyze_sku(sku: str, current_user: dict = Depends(get_current_user)):
    """
    Run full agent analysis for a specific SKU.
    
    This endpoint:
    1. Retrieves current inventory status
    2. Generates demand forecast
    3. Assesses supply risk
    4. Decides whether to restock or hold
    5. Drafts negotiation email if restocking is needed
    
    Returns a complete AgentResponse with all analysis data.
    """
    df = load_supply_chain_data()
    
    # Step 1: Get inventory status
    try:
        inventory = get_inventory_for_sku(df, sku)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU '{sku}' not found in inventory."
        )
    
    # Step 2: Run demand forecast
    try:
        forecast = run_demand_forecast(df, sku)
    except HTTPException as e:
        # If no sales history, estimate demand as 30% of current stock over 30 days
        logger.warning(f"No forecast available for {sku}, using estimated demand")
        estimated_demand = max(int(inventory['current_stock'] * 0.3), 10)
        forecast = {
            "sku": sku,
            "forecasted_demand_30_days": estimated_demand,
            "plot_data": []
        }
    
    # Step 3: Assess supply risk
    risk = calculate_supply_risk(
        inventory['defect_rate'],
        inventory['lead_time_days']
    )
    
    # Step 4: Decision logic
    current_stock = inventory['current_stock']
    forecasted_demand = forecast['forecasted_demand_30_days']
    
    # Calculate statistical safety stock using InventoryOptimizer
    try:
        from src.inventory_optimizer import InventoryOptimizer
        optimizer = InventoryOptimizer()
        
        # Get historical demands list from dataframe
        sku_df = df[df['SKU'] == sku]
        daily_demands = sku_df['Quantity_Sold'].dropna().tolist() if not sku_df.empty else []
        
        metrics = optimizer.full_analysis(
            sku=sku,
            product_name=inventory['product_name'],
            current_stock=current_stock,
            daily_demands=daily_demands if daily_demands else [forecasted_demand / 30.0],
            lead_time_days=inventory['lead_time_days'],
            unit_cost=inventory['cost_per_unit']
        )
        safety_buffer = metrics.safety_stock
    except Exception as calc_err:
        logger.warning(f"Fallback safety stock in analyze endpoint: {calc_err}")
        safety_buffer = int(forecasted_demand * 0.2)
        
    required_stock = forecasted_demand + safety_buffer
    
    # Determine decision
    if required_stock > current_stock:
        decision = "Restock"
        units_needed = required_stock - current_stock
        confidence = min(0.95, 0.7 + (units_needed / max(1, forecasted_demand)) * 0.25)
        reasoning = (
            f"Forecasted 30-day demand ({forecasted_demand} units) plus dynamic statistical safety buffer "
            f"({safety_buffer} units) exceeds current stock ({current_stock} units). "
            f"Recommend ordering {units_needed} additional units. "
            f"Supplier risk level: {risk['risk_level']}."
        )
        
        # Step 5: Draft email for restock decision
        email_draft = generate_email_with_gemini(
            product_name=inventory['product_name'],
            supplier_name=inventory['supplier'],
            required_units=units_needed,
            reason=f"Stockout risk detected. Current: {current_stock}, Required: {required_stock}"
        )
    else:
        decision = "Hold"
        confidence = 0.85
        reasoning = (
            f"Current stock ({current_stock} units) is sufficient to meet "
            f"forecasted 30-day demand ({forecasted_demand} units) with safety buffer. "
            f"No immediate procurement action required."
        )
        email_draft = None
    
    # Build response
    response = AgentResponse(
        sku=sku,
        product_name=inventory['product_name'],
        decision=decision,
        confidence_score=round(confidence, 2),
        reasoning=reasoning,
        current_stock=current_stock,
        forecasted_demand=forecasted_demand,
        risk_assessment=RiskAssessment(**risk),
        email_draft=EmailDraft(**email_draft) if email_draft else None,
        plot_data=[ForecastDataPoint(**dp) for dp in forecast['plot_data']]
    )
    
    logger.info(f"Agent analysis complete for {sku}: {decision}")
    return response


@app.post("/api/agent/analyze-all", tags=["Agent"])
async def analyze_all_skus(current_user: dict = Depends(get_current_user)):
    """
    Run agent analysis for all SKUs in the inventory.
    Returns a list of AgentResponse objects.
    """
    df = load_supply_chain_data()
    skus = df['SKU'].unique().tolist()
    
    results = []
    for sku in skus:
        try:
            result = await analyze_sku(sku)
            results.append(result.model_dump())
        except HTTPException as e:
            logger.warning(f"Analysis failed for {sku}: {e.detail}")
            results.append({
                "sku": sku,
                "error": e.detail
            })
    
    return {
        "total_analyzed": len(results),
        "results": results
    }


# =============================================================================
# GEMINI-POWERED SKU ANALYSIS (GET /api/v2/analyze/{sku})
# =============================================================================

@app.get("/api/v2/analyze/{sku}", tags=["Enhanced Analysis"])
async def gemini_analyze_sku_endpoint(sku: str):
    """
    AI-powered SKU analysis using Gemini.
    Returns MSME-friendly explanation, reorder urgency, and recommendation
    alongside key inventory metrics.
    """
    try:
        df = load_supply_chain_data()

        # Locate the SKU
        sku_df = df[df['SKU'].str.upper() == sku.upper()]
        if sku_df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found in inventory."
            )

        rec = sku_df.iloc[0]

        # Calculate avg daily sales
        sales = sku_df[['Sales_Date', 'Quantity_Sold']].copy()
        sales['Sales_Date'] = pd.to_datetime(sales['Sales_Date'])
        total_sold = float(sales['Quantity_Sold'].sum())
        date_range = (sales['Sales_Date'].max() - sales['Sales_Date'].min()).days
        num_days = max(date_range, 1)
        avg_daily_sales = total_sold / num_days if num_days > 0 else 0

        current_stock = int(rec['Current_Stock'])
        days_of_stock = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else 999

        sku_data = {
            "sku": str(rec['SKU']),
            "product_name": str(rec['Product_Name']),
            "category": str(rec['Category']),
            "current_stock": current_stock,
            "cost_per_unit": float(rec['Cost_Per_Unit']),
            "supplier": str(rec['Supplier']),
            "defect_rate": float(rec['Defect_Rate']),
            "lead_time_days": int(rec['Lead_Time_Days']),
            "avg_daily_sales": round(avg_daily_sales, 2),
            "days_of_stock": round(days_of_stock, 1),
        }

        # Run demand forecast (fallback if unavailable)
        try:
            forecast_data = run_demand_forecast(df, sku)
        except Exception as e:
            logger.warning(f"Forecast failed for {sku}: {e}")
            forecast_data = {
                "sku": sku,
                "forecasted_demand_30_days": max(int(current_stock * 0.3), 10),
                "plot_data": [],
            }

        # Call Gemini analysis from agent_logic with error handling
        try:
            from src.agent_logic import gemini_analyze_sku, _fallback_analysis
            analysis = gemini_analyze_sku(sku_data, forecast_data)
        except Exception as e:
            logger.error(f"AI analysis failed for {sku}: {e}")
            # Use fallback analysis if Gemini fails
            try:
                from src.agent_logic import _fallback_analysis
                analysis = _fallback_analysis(sku_data, forecast_data)
            except Exception as fallback_error:
                logger.error(f"Fallback analysis also failed: {fallback_error}")
                # Ultimate fallback - return basic analysis
                analysis = {
                    "explanation": f"{sku_data['product_name']} has {current_stock} units in stock with approximately {sku_data['days_of_stock']} days of stock remaining.",
                    "reorderUrgency": "Medium" if days_of_stock < 14 else "Low",
                    "recommendation": "Review stock levels and consider ordering based on recent sales trends.",
                }

        return {
            "sku": sku_data["sku"],
            "product_name": sku_data["product_name"],
            "current_stock": current_stock,
            "avg_daily_sales": sku_data["avg_daily_sales"],
            "days_of_stock": sku_data["days_of_stock"],
            "forecasted_demand_30_days": forecast_data["forecasted_demand_30_days"],
            "explanation": analysis.get("explanation", "Analysis unavailable"),
            "reorderUrgency": analysis.get("reorderUrgency", "Unknown"),
            "recommendation": analysis.get("recommendation", "Please review manually"),
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in AI analysis for {sku}: {e}", exc_info=True)
        # Return a graceful error response instead of 500
        return {
            "sku": sku,
            "product_name": "Unknown",
            "current_stock": 0,
            "avg_daily_sales": 0,
            "days_of_stock": 0,
            "forecasted_demand_30_days": 0,
            "explanation": f"Analysis temporarily unavailable. Error: {str(e)[:100]}",
            "reorderUrgency": "Unknown",
            "recommendation": "Please try again later or contact support.",
        }


# =============================================================================
# EMAIL ENDPOINTS
# =============================================================================

@app.get("/api/email/config", response_model=EmailConfigResponse, tags=["Email"])
async def get_email_config():
    """
    Check email configuration status.
    Returns whether email is configured and the sender address.
    """
    return EmailConfigResponse(
        configured=EMAIL_CONFIGURED,
        email_address=SMTP_EMAIL if EMAIL_CONFIGURED else None,
        smtp_host=SMTP_HOST,
        smtp_port=SMTP_PORT
    )


@app.post("/api/email/send", response_model=EmailSendResponse, tags=["Email"])
async def send_email(request: EmailSendRequest):
    """
    Send an email to a supplier.
    
    Requires SMTP_EMAIL and SMTP_PASSWORD environment variables to be set.
    For Gmail, use an App Password (not your regular password).
    """
    import uuid
    
    # Use default recipient if configured and no recipient specified
    to_email = request.to_email or SMTP_RECIPIENT
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recipient email provided. Set to_email or configure SMTP_RECIPIENT."
        )
    
    # Send the email
    result = send_email_smtp(
        to_email=to_email,
        subject=request.subject,
        body=request.body
    )
    
    email_id = f"OPT-{uuid.uuid4().hex[:8].upper()}"
    
    if result.get("simulated"):
        # Email not configured - return simulated response
        return EmailSendResponse(
            success=True,
            message="Email simulated (SMTP not configured). Set SMTP_EMAIL and SMTP_PASSWORD to enable.",
            email_id=email_id,
            sent_at=datetime.now().isoformat(),
            from_email="not-configured@optistock.demo",
            to_email=to_email
        )
    
    if result["success"]:
        return EmailSendResponse(
            success=True,
            message=result["message"],
            email_id=email_id,
            sent_at=datetime.now().isoformat(),
            from_email=SMTP_EMAIL,
            to_email=to_email
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"]
        )


@app.post("/api/email/test", tags=["Email"])
async def test_email():
    """
    Send a test email to verify SMTP configuration.
    Sends to SMTP_RECIPIENT or the sender's own address.
    """
    if not EMAIL_CONFIGURED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not configured. Set SMTP_EMAIL and SMTP_PASSWORD environment variables."
        )
    
    test_recipient = SMTP_RECIPIENT or SMTP_EMAIL
    test_subject = "🧪 OptiStock Email Test"
    test_body = f"""
Hello!

This is a test email from OptiStock Procurement Agent.

✅ Your email configuration is working correctly!

Configuration Details:
- SMTP Host: {SMTP_HOST}
- SMTP Port: {SMTP_PORT}
- Sender: {SMTP_EMAIL}
- Timestamp: {datetime.now().isoformat()}

Best regards,
OptiStock System
    """.strip()
    
    result = send_email_smtp(test_recipient, test_subject, test_body)
    
    if result["success"]:
        return {
            "success": True,
            "message": f"Test email sent to {test_recipient}",
            "details": result
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"]
        )


@app.post("/api/agent/analyze-and-send/{sku}", tags=["Agent"])
async def analyze_and_send_email(sku: str, recipient_email: Optional[str] = None):
    """
    Full autonomous agent flow:
    1. Analyze SKU for stockout risk
    2. If RESTOCK decision, generate and SEND email to supplier
    
    This is the full autonomous procurement cycle.
    """
    # Run analysis
    analysis = await analyze_sku(sku)
    
    result = {
        "analysis": analysis.model_dump(),
        "email_sent": False,
        "email_result": None
    }
    
    # If decision is to restock and email was drafted, send it
    if analysis.decision == "Restock" and analysis.email_draft:
        to_email = recipient_email or SMTP_RECIPIENT
        
        if to_email:
            email_result = send_email_smtp(
                to_email=to_email,
                subject=analysis.email_draft.subject,
                body=analysis.email_draft.body
            )
            result["email_sent"] = email_result.get("success", False)
            result["email_result"] = email_result
            
            if email_result.get("success"):
                logger.info(f"🤖 Agent auto-sent procurement email for {sku} to {to_email}")
        else:
            result["email_result"] = {
                "success": False,
                "message": "No recipient email. Provide recipient_email parameter or set SMTP_RECIPIENT."
            }
    
    return result


# =============================================================================
# UNIVERSAL FILE UPLOAD ENDPOINT
# =============================================================================

from fastapi import UploadFile, File
import io
import json
import xml.etree.ElementTree as ET

# Supported file extensions
SUPPORTED_EXTENSIONS = ['.csv', '.json', '.xml', '.txt', '.pdf', '.xlsx', '.xls', '.png', '.jpg', '.jpeg', '.log']

def parse_json_to_dataframe(content: str) -> pd.DataFrame:
    """Parse JSON content to DataFrame using intelligent analysis."""
    data = json.loads(content)
    logger.info(f"Parsing JSON data of type: {type(data).__name__}")
    
    # Helper function to flatten nested objects
    def flatten_dict(d, parent_key='', sep='_'):
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    # Helper function to find array of records in nested structure
    def find_records_array(obj, depth=0):
        if depth > 5:  # Limit recursion depth
            return None
        
        if isinstance(obj, list) and len(obj) > 0:
            # Check if it's a list of dicts (records)
            if isinstance(obj[0], dict):
                return obj
            return None
        
        if isinstance(obj, dict):
            # Check common keys for data arrays
            common_keys = ['data', 'items', 'products', 'inventory', 'records', 'results', 
                          'entries', 'rows', 'list', 'content', 'values', 'orders', 
                          'transactions', 'stock', 'supplies', 'goods']
            
            for key in common_keys:
                if key in obj and isinstance(obj[key], list) and len(obj[key]) > 0:
                    if isinstance(obj[key][0], dict):
                        return obj[key]
            
            # Search recursively in all values
            for key, value in obj.items():
                result = find_records_array(value, depth + 1)
                if result:
                    return result
        
        return None
    
    records = None
    
    # Try to find records array in the JSON structure
    if isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            records = data
        elif len(data) > 0 and isinstance(data[0], list):
            # Array of arrays - first row might be headers
            if len(data) > 1:
                headers = [str(h) for h in data[0]]
                records = [dict(zip(headers, row)) for row in data[1:]]
    elif isinstance(data, dict):
        records = find_records_array(data)
        
        # If no records found, check if the dict itself represents a single record or table
        if records is None:
            # Check if values are all arrays of same length (columnar format)
            values = list(data.values())
            if all(isinstance(v, list) for v in values):
                lengths = [len(v) for v in values]
                if len(set(lengths)) == 1 and lengths[0] > 0:
                    # Columnar format - convert to records
                    records = []
                    for i in range(lengths[0]):
                        record = {k: v[i] for k, v in data.items()}
                        records.append(record)
            else:
                # Might be a single record
                records = [data]
    
    if records and len(records) > 0:
        # Flatten any nested dicts in records
        flattened_records = []
        for record in records:
            if isinstance(record, dict):
                flattened_records.append(flatten_dict(record))
            else:
                flattened_records.append({'value': record})
        
        df = pd.DataFrame(flattened_records)
        logger.info(f"Parsed JSON with {len(df)} records, columns: {list(df.columns)}")
        return df
    
    raise ValueError("Could not extract records from JSON structure")


def parse_json_with_ai(content: str) -> pd.DataFrame:
    """Use AI to intelligently parse JSON and extract inventory data."""
    logger.info("Using AI to analyze JSON structure and extract inventory data")
    
    extraction_prompt = f"""Analyze this JSON data and extract ALL inventory/product information into a standardized format.

The JSON may contain:
- Product catalogs, inventory lists, stock data, order records, or any product-related information
- Nested structures, arrays, or complex formats
- Various field names for the same concept (e.g., 'qty', 'quantity', 'stock', 'units' all mean quantity)

Extract EVERY item/product found and map to these fields (use exact values, don't make up data):
- sku: Product ID, SKU, item code, product code, etc.
- product_name: Name, title, description, item name, etc.
- category: Category, type, class, group, etc.
- current_stock: Stock, quantity, qty, units, inventory level, available, etc.
- cost_per_unit: Price, cost, unit price, rate, amount, etc.
- supplier: Supplier, vendor, manufacturer, brand, source, etc.
- defect_rate: Defect rate, error rate, rejection rate (as decimal, e.g., 0.02 for 2%)
- lead_time_days: Lead time, delivery days, shipping time, etc.
- sales_date: Date, sale date, order date, transaction date, etc.
- quantity_sold: Sold, sales quantity, units sold, etc.

Return a valid JSON array with all extracted items.
Example output format:
[
  {{"sku": "ABC123", "product_name": "Laptop", "category": "Electronics", "current_stock": 50, "cost_per_unit": 999.99, "supplier": "TechCorp"}},
  {{"sku": "DEF456", "product_name": "Chair", "category": "Furniture", "current_stock": 100, "cost_per_unit": 149.99}}
]

IMPORTANT:
- Extract ALL items found in the data
- Use EXACT values from the JSON - do not make up or modify values
- If a field is not present for an item, omit it from that item's object
- Handle nested structures by extracting the relevant data
- If quantities/prices are strings with currency symbols, extract just the number

JSON DATA TO ANALYZE:
```json
{content[:20000]}
```

Return ONLY the JSON array, no explanations or markdown."""

    try:
        import time
        
        # Try different models in order of preference
        models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash']
        ai_response = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                logger.info(f"JSON parsing - Trying model: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(extraction_prompt)
                ai_response = response.text.strip()
                logger.info(f"Successfully got response from {model_name}")
                break
            except Exception as model_error:
                error_str = str(model_error)
                last_error = model_error
                logger.warning(f"Model {model_name} failed: {error_str[:200]}")
                
                # If quota error, wait and retry
                if 'quota' in error_str.lower() or 'rate' in error_str.lower() or '429' in error_str:
                    logger.info("Quota exceeded, waiting 10 seconds before trying next model...")
                    time.sleep(10)
                continue
        
        if ai_response is None:
            # Check if it's a quota error
            error_str = str(last_error) if last_error else ""
            if 'quota' in error_str.lower() or 'rate' in error_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="AI API quota exceeded. Please wait a minute and try again, or upload a CSV/Excel file instead which doesn't require AI processing."
                )
            raise last_error or Exception("All AI models failed")
        
        # Clean up the response
        if '```json' in ai_response:
            ai_response = ai_response.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_response:
            ai_response = ai_response.split('```')[1].split('```')[0].strip()
        
        # Parse JSON response
        extracted_data = json.loads(ai_response)
        
        if isinstance(extracted_data, list) and len(extracted_data) > 0:
            df = pd.DataFrame(extracted_data)
            logger.info(f"AI extracted {len(df)} items from JSON")
            logger.info(f"Columns: {list(df.columns)}")
            return df
        else:
            raise ValueError("AI returned empty or invalid data")
            
    except Exception as e:
        logger.error(f"AI JSON parsing failed: {e}")
        raise


def parse_xml_to_dataframe(content: str) -> pd.DataFrame:
    """Parse XML content to DataFrame."""
    root = ET.fromstring(content)
    
    # Find all record elements (try common names)
    records = []
    for tag in ['item', 'product', 'record', 'row', 'entry']:
        items = root.findall(f'.//{tag}')
        if items:
            for item in items:
                record = {}
                for child in item:
                    record[child.tag] = child.text
                records.append(record)
            break
    
    # If no records found, try direct children
    if not records:
        for child in root:
            record = {}
            for elem in child:
                record[elem.tag] = elem.text
            if record:
                records.append(record)
    
    if not records:
        raise ValueError("Could not parse XML structure")
    
    return pd.DataFrame(records)

def parse_text_to_dataframe(content: str) -> pd.DataFrame:
    """Parse plain text content to DataFrame using intelligent detection."""
    lines = content.strip().split('\n')
    
    # Try to detect delimiter
    delimiters = [',', '\t', '|', ';']
    best_delimiter = ','
    max_cols = 0
    
    for delim in delimiters:
        cols = len(lines[0].split(delim))
        if cols > max_cols:
            max_cols = cols
            best_delimiter = delim
    
    # Parse as CSV with detected delimiter
    return pd.read_csv(io.StringIO(content), sep=best_delimiter)

def infer_category(product_name: str) -> str:
    """Infer product category from product name."""
    name_lower = product_name.lower() if product_name else ''
    
    categories = {
        'Electronics': ['laptop', 'phone', 'computer', 'tablet', 'monitor', 'keyboard', 'mouse', 'camera', 'headphone', 'speaker', 'tv', 'television'],
        'Furniture': ['chair', 'table', 'desk', 'sofa', 'bed', 'cabinet', 'shelf', 'drawer'],
        'Clothing': ['shirt', 'pants', 'dress', 'jacket', 'coat', 'shoes', 'hat', 'socks'],
        'Food': ['rice', 'bread', 'milk', 'juice', 'snack', 'fruit', 'vegetable', 'meat'],
        'Office Supplies': ['pen', 'paper', 'stapler', 'folder', 'notebook', 'printer', 'ink'],
        'Tools': ['hammer', 'drill', 'saw', 'wrench', 'screwdriver', 'plier'],
        'Healthcare': ['medicine', 'vitamin', 'bandage', 'mask', 'sanitizer', 'thermometer'],
    }
    
    for category, keywords in categories.items():
        if any(kw in name_lower for kw in keywords):
            return category
    
    return 'General'

def safe_get_series(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Safely get a column as a Series, handling duplicate column names."""
    col = df[col_name]
    if isinstance(col, pd.DataFrame):
        return col.iloc[:, 0]  # Take first column if duplicates exist
    return col

def normalize_to_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize any DataFrame to OptiStock schema - PRESERVING EXACT VALUES when available."""
    
    # Ensure we have a proper DataFrame
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"Expected DataFrame, got {type(df).__name__}")
    
    # Reset index to avoid issues with duplicate indices
    df = df.reset_index(drop=True).copy()
    
    # Handle duplicate column names by making them unique
    if df.columns.duplicated().any():
        cols = pd.Series(df.columns)
        for dup in cols[cols.duplicated()].unique():
            dups = cols[cols == dup].index.tolist()
            for i, idx in enumerate(dups[1:], 1):
                cols.iloc[idx] = f"{dup}_{i}"
        df.columns = cols
    
    logger.info(f"Normalizing DataFrame with columns: {list(df.columns)}")
    logger.info(f"Original data preview (first 3 rows):\n{df.head(3).to_string()}")
    
    # Column mapping for common variations (including AI-generated field names)
    column_mappings = {
        'SKU': ['sku', 'product_id', 'item_id', 'item_code', 'id', 'code', 'productid', 'itemid', 
                'product id', 'item id', 'productcode', 'product_code', 'article_number', 'article_no',
                'part_number', 'part_no', 'upc', 'barcode', 'asin'],
        'Product_Name': ['product_name', 'name', 'product', 'item_name', 'item', 'productname', 
                        'itemname', 'description', 'title', 'product name', 'item name', 'product_title',
                        'item_description', 'goods_name', 'material_name', 'article_name'],
        'Category': ['category', 'type', 'product_category', 'cat', 'group', 'class', 'product_type',
                    'item_category', 'product_group', 'classification', 'segment', 'department'],
        'Current_Stock': ['current_stock', 'stock', 'quantity', 'qty', 'inventory', 'in_stock', 
                         'available', 'units', 'current stock', 'stock level', 'inventory_level',
                         'on_hand', 'available_qty', 'stock_quantity', 'units_in_stock', 'balance'],
        'Cost_Per_Unit': ['cost_per_unit', 'cost', 'unit_cost', 'price', 'unit_price', 'buying_price', 
                         'purchase_price', 'cost per unit', 'unit price', 'rate', 'unit_rate',
                         'selling_price', 'mrp', 'amount', 'value', 'cost_price'],
        'Supplier': ['supplier', 'vendor', 'supplier_name', 'vendor_name', 'manufacturer', 'brand',
                    'source', 'distributor', 'seller', 'provider', 'company', 'manufacturer_name'],
        'Defect_Rate': ['defect_rate', 'defect', 'defects', 'defective', 'error_rate', 'reject_rate', 
                       'defect rate', 'rejection_rate', 'failure_rate', 'quality_rate'],
        'Lead_Time_Days': ['lead_time_days', 'lead_time', 'leadtime', 'delivery_days', 'shipping_days', 
                          'lead time', 'lead time days', 'delivery_time', 'shipping_time', 'transit_days'],
        'Sales_Date': ['sales_date', 'date', 'sale_date', 'order_date', 'transaction_date', 'sales date',
                      'purchase_date', 'created_date', 'entry_date', 'record_date'],
        'Quantity_Sold': ['quantity_sold', 'sold', 'sales', 'qty_sold', 'units_sold', 'sales_qty', 
                         'quantity sold', 'sold_quantity', 'sales_quantity', 'sold_units']
    }
    
    # Rename columns based on mapping
    rename_map = {}
    mapped_targets = set()  # Track which target columns have already been mapped
    
    for col in df.columns:
        col_lower = col.lower().replace(' ', '_').replace('-', '_')
        col_lower_spaces = col.lower().strip()
        col_no_underscore = col.lower().replace('_', '').replace(' ', '')
        
        for target_col, variations in column_mappings.items():
            # Skip if this target column is already mapped
            if target_col in mapped_targets:
                continue
                
            # Also check without underscores for more flexible matching
            variations_no_underscore = [v.replace('_', '').replace(' ', '') for v in variations]
            
            if (col_lower in variations or 
                col_lower_spaces in variations or 
                col.strip().lower() in variations or
                col_no_underscore in variations_no_underscore):
                if col not in rename_map:
                    rename_map[col] = target_col
                    mapped_targets.add(target_col)
                    logger.info(f"Mapping column '{col}' -> '{target_col}'")
                break
    
    df = df.rename(columns=rename_map)
    
    # Handle any duplicate columns created by renaming (drop duplicates, keep first)
    if df.columns.duplicated().any():
        logger.warning(f"Duplicate columns detected after rename: {df.columns[df.columns.duplicated()].tolist()}")
        df = df.loc[:, ~df.columns.duplicated(keep='first')]
    
    # Generate SKU if missing - but keep original if it exists
    if 'SKU' not in df.columns:
        # Look for any column that might be an ID
        for col in df.columns:
            if df[col].dtype == 'object' and df[col].nunique() == len(df):
                df['SKU'] = df[col].astype(str)
                logger.info(f"Using column '{col}' as SKU")
                break
        else:
            df['SKU'] = [f'SKU-{str(i+1).zfill(4)}' for i in range(len(df))]
            logger.info("Generated SKU values")
    else:
        # Preserve exact SKU values - handle both Series and potential DataFrame
        sku_col = df['SKU']
        if isinstance(sku_col, pd.DataFrame):
            sku_col = sku_col.iloc[:, 0]  # Take first column if duplicates exist
        df['SKU'] = sku_col.astype(str).str.strip()
        logger.info(f"Preserving SKU values: {df['SKU'].tolist()[:5]}...")
    
    # Generate Product_Name if missing
    if 'Product_Name' not in df.columns:
        text_cols = [col for col in df.columns if col not in ['SKU'] and df[col].dtype == 'object']
        if text_cols:
            prod_col = df[text_cols[0]]
            if isinstance(prod_col, pd.DataFrame):
                prod_col = prod_col.iloc[:, 0]
            df['Product_Name'] = prod_col.astype(str).str.strip()
            logger.info(f"Using column '{text_cols[0]}' as Product_Name")
        else:
            df['Product_Name'] = [f'Product {i+1}' for i in range(len(df))]
    else:
        prod_col = df['Product_Name']
        if isinstance(prod_col, pd.DataFrame):
            prod_col = prod_col.iloc[:, 0]
        df['Product_Name'] = prod_col.astype(str).str.strip()
        logger.info(f"Preserving Product_Name values: {df['Product_Name'].tolist()[:5]}...")
    
    # Infer Category if missing
    if 'Category' not in df.columns:
        df['Category'] = df['Product_Name'].apply(infer_category)
    else:
        df['Category'] = safe_get_series(df, 'Category').astype(str).str.strip()
        df['Category'] = df['Category'].replace('', 'General').fillna('General')
    
    # Handle numeric columns - PRESERVE EXACT VALUES, only fill if truly missing
    if 'Current_Stock' not in df.columns:
        df['Current_Stock'] = 100
    else:
        # Preserve exact values, only fill NaN
        df['Current_Stock'] = pd.to_numeric(safe_get_series(df, 'Current_Stock').astype(str).str.replace(',', ''), errors='coerce')
        original_count = df['Current_Stock'].notna().sum()
        df['Current_Stock'] = df['Current_Stock'].fillna(100)
        logger.info(f"Current_Stock: {original_count} exact values preserved")
    
    if 'Cost_Per_Unit' not in df.columns:
        df['Cost_Per_Unit'] = 0
    else:
        # Remove currency symbols and preserve exact values
        df['Cost_Per_Unit'] = safe_get_series(df, 'Cost_Per_Unit').astype(str).str.replace(r'[₹$€£,]', '', regex=True)
        df['Cost_Per_Unit'] = pd.to_numeric(df['Cost_Per_Unit'], errors='coerce')
        original_count = df['Cost_Per_Unit'].notna().sum()
        df['Cost_Per_Unit'] = df['Cost_Per_Unit'].fillna(0)
        logger.info(f"Cost_Per_Unit: {original_count} exact values preserved")
    
    if 'Supplier' not in df.columns:
        df['Supplier'] = 'Unknown Supplier'
    else:
        df['Supplier'] = safe_get_series(df, 'Supplier').astype(str).str.strip()
        df['Supplier'] = df['Supplier'].replace(['', 'nan', 'None'], 'Unknown Supplier')
    
    if 'Defect_Rate' not in df.columns:
        df['Defect_Rate'] = 0.02
    else:
        df['Defect_Rate'] = safe_get_series(df, 'Defect_Rate').astype(str).str.replace('%', '')
        df['Defect_Rate'] = pd.to_numeric(df['Defect_Rate'], errors='coerce')
        # Convert percentage to decimal if needed
        df.loc[df['Defect_Rate'] > 1, 'Defect_Rate'] = df.loc[df['Defect_Rate'] > 1, 'Defect_Rate'] / 100
        df['Defect_Rate'] = df['Defect_Rate'].fillna(0.02)
    
    if 'Lead_Time_Days' not in df.columns:
        df['Lead_Time_Days'] = 7
    else:
        df['Lead_Time_Days'] = pd.to_numeric(safe_get_series(df, 'Lead_Time_Days').astype(str).str.replace(',', ''), errors='coerce')
        df['Lead_Time_Days'] = df['Lead_Time_Days'].fillna(7)
    
    if 'Sales_Date' not in df.columns:
        df['Sales_Date'] = datetime.now().strftime('%Y-%m-%d')
    else:
        df['Sales_Date'] = safe_get_series(df, 'Sales_Date').astype(str).str.strip()
        df['Sales_Date'] = df['Sales_Date'].replace(['', 'nan', 'None', 'NaT'], datetime.now().strftime('%Y-%m-%d'))
    
    if 'Quantity_Sold' not in df.columns:
        df['Quantity_Sold'] = 0
    else:
        df['Quantity_Sold'] = pd.to_numeric(safe_get_series(df, 'Quantity_Sold').astype(str).str.replace(',', ''), errors='coerce')
        df['Quantity_Sold'] = df['Quantity_Sold'].fillna(0)
    
    # Fill any remaining NaN values in text columns
    df['Product_Name'] = df['Product_Name'].replace(['', 'nan', 'None'], 'Unknown Product').fillna('Unknown Product')
    df['Category'] = df['Category'].replace(['', 'nan', 'None'], 'General').fillna('General')
    df['Supplier'] = df['Supplier'].replace(['', 'nan', 'None'], 'Unknown Supplier').fillna('Unknown Supplier')
    
    # Select final columns in order
    final_columns = ['SKU', 'Product_Name', 'Category', 'Current_Stock', 'Cost_Per_Unit', 
                     'Supplier', 'Defect_Rate', 'Lead_Time_Days', 'Sales_Date', 'Quantity_Sold']
    
    result_df = df[final_columns]
    logger.info(f"Final normalized data preview:\n{result_df.head(3).to_string()}")
    
    return result_df


@app.post("/api/upload", tags=["Data"])
async def upload_universal_file(file: UploadFile = File(...)):
    """
    Universal file upload endpoint.
    Accepts: CSV, JSON, XML, TXT, PDF, Excel, Images, Log files.
    Automatically detects format, parses content, and normalizes to OptiStock schema.
    Missing values are intelligently imputed.
    """
    filename = file.filename.lower()
    ext = '.' + filename.split('.')[-1] if '.' in filename else ''
    
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    
    try:
        contents = await file.read()
        content_str = None
        df = None
        format_detected = ext[1:].upper()
        
        # Parse based on file type
        if ext == '.csv':
            content_str = contents.decode('utf-8')
            df = pd.read_csv(io.StringIO(content_str))
            
        elif ext == '.json':
            content_str = contents.decode('utf-8')
            
            # First try standard parsing
            try:
                df = parse_json_to_dataframe(content_str)
                
                # Check if parsing was successful - verify we got meaningful data
                if df is not None and len(df) > 0:
                    # Check if we have any recognizable inventory columns
                    df_cols_lower = [col.lower().replace('_', '').replace(' ', '') for col in df.columns]
                    inventory_keywords = ['sku', 'product', 'name', 'item', 'stock', 'quantity', 'price', 'cost', 'supplier', 'category']
                    has_inventory_cols = any(any(kw in col for kw in inventory_keywords) for col in df_cols_lower)
                    
                    if not has_inventory_cols:
                        logger.info("Standard JSON parsing found no inventory columns, trying AI")
                        raise ValueError("No inventory columns found")
                        
            except Exception as parse_error:
                logger.warning(f"Standard JSON parsing issue: {parse_error}")
                
                # Use AI to intelligently parse the JSON
                if GEMINI_API_KEY:
                    try:
                        df = parse_json_with_ai(content_str)
                    except Exception as ai_error:
                        logger.error(f"AI JSON parsing also failed: {ai_error}")
                        # Re-raise the original error if AI also fails
                        raise parse_error
                else:
                    raise parse_error
            
        elif ext == '.xml':
            content_str = contents.decode('utf-8')
            df = parse_xml_to_dataframe(content_str)
            
        elif ext in ['.txt', '.log']:
            content_str = contents.decode('utf-8')
            df = parse_text_to_dataframe(content_str)
            
        elif ext in ['.xlsx', '.xls']:
            # Excel files
            try:
                import openpyxl
                df = pd.read_excel(io.BytesIO(contents))
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Excel support requires openpyxl. Install with: pip install openpyxl"
                )
                
        elif ext == '.pdf':
            # PDF files - ALWAYS use AI to intelligently extract data
            try:
                import pdfplumber
                
                all_text_content = []
                all_tables_text = []
                
                with pdfplumber.open(io.BytesIO(contents)) as pdf:
                    logger.info(f"Processing PDF with {len(pdf.pages)} pages")
                    
                    for page_num, page in enumerate(pdf.pages):
                        # Extract ALL text from page
                        text = page.extract_text()
                        if text:
                            all_text_content.append(f"--- Page {page_num + 1} ---\n{text}")
                        
                        # Also try to extract tables and convert to text format
                        page_tables = page.extract_tables()
                        if page_tables:
                            for table in page_tables:
                                if table and len(table) > 0:
                                    table_text = "\n".join([" | ".join([str(cell) if cell else "" for cell in row]) for row in table])
                                    all_tables_text.append(f"Table from page {page_num + 1}:\n{table_text}")
                
                # Combine all extracted content
                full_text = '\n\n'.join(all_text_content)
                tables_text = '\n\n'.join(all_tables_text)
                combined_content = f"{full_text}\n\n{tables_text}" if tables_text else full_text
                
                logger.info(f"Extracted {len(full_text)} chars of text, {len(tables_text)} chars of table data from PDF")
                
                if not combined_content.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Could not extract any text from the PDF. The PDF might be scanned/image-based."
                    )
                
                # ALWAYS use AI to analyze PDF content intelligently
                if GEMINI_API_KEY:
                    logger.info("Using AI agent to intelligently analyze PDF and extract inventory data")
                    
                    extraction_prompt = f"""You are an intelligent data extraction agent. Analyze this PDF content and extract ALL inventory/product/item data.

IMPORTANT INSTRUCTIONS:
1. Look for ANY data that could be inventory, products, stock, items, orders, or similar
2. The data might be in tables, paragraphs, lists, or mixed formats
3. Extract EVERY item you can find - be thorough
4. Use the EXACT values from the text - do not make up or modify any data
5. Handle different formats: "Product: X", "Item - Y", numbered lists, bullet points, etc.

For each item found, extract these fields (use exact values from text):
- sku: Any ID, code, SKU, product number, item number, reference number
- product_name: Name, title, description, item name
- category: Category, type, class, department, group
- current_stock: Stock level, quantity, qty, units, inventory, available, on-hand
- cost_per_unit: Price, cost, rate, amount, value (extract number only)
- supplier: Supplier, vendor, manufacturer, brand, company
- defect_rate: Defect rate, error rate (as decimal like 0.02)
- lead_time_days: Lead time, delivery days, shipping days (number only)
- quantity_sold: Units sold, sales quantity, sold amount

Return a valid JSON array. Example:
[
  {{"sku": "ABC123", "product_name": "Widget A", "category": "Electronics", "current_stock": 150, "cost_per_unit": 29.99, "supplier": "Acme Corp"}},
  {{"sku": "XYZ789", "product_name": "Gadget B", "current_stock": 75, "cost_per_unit": 49.99}}
]

RULES:
- If you find product names but no SKUs, generate simple SKUs like "ITEM001", "ITEM002"
- Extract numbers from strings like "₹500" → 500, "$99.99" → 99.99, "50 units" → 50
- If data is in a table format, extract each row as a separate item
- Include ALL items even if they have incomplete data
- Return empty array [] ONLY if absolutely no inventory data exists

PDF CONTENT TO ANALYZE:
\"\"\"
{combined_content[:25000]}
\"\"\"

Return ONLY the JSON array, nothing else."""

                    try:
                        import time
                        
                        # Try different models in order of preference
                        models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash']
                        ai_response = None
                        last_error = None
                        
                        for model_name in models_to_try:
                            try:
                                logger.info(f"Trying model: {model_name}")
                                model = genai.GenerativeModel(model_name)
                                response = model.generate_content(extraction_prompt)
                                ai_response = response.text.strip()
                                logger.info(f"Successfully got response from {model_name}")
                                break
                            except Exception as model_error:
                                error_str = str(model_error)
                                last_error = model_error
                                logger.warning(f"Model {model_name} failed: {error_str[:200]}")
                                
                                # If quota error, wait and retry
                                if 'quota' in error_str.lower() or 'rate' in error_str.lower() or '429' in error_str:
                                    logger.info("Quota exceeded, waiting 10 seconds before trying next model...")
                                    time.sleep(10)
                                continue
                        
                        if ai_response is None:
                            # Check if it's a quota error
                            error_str = str(last_error) if last_error else ""
                            if 'quota' in error_str.lower() or 'rate' in error_str.lower():
                                raise HTTPException(
                                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="AI API quota exceeded. Please wait a minute and try again, or upload a CSV/Excel file instead which doesn't require AI processing."
                                )
                            raise last_error or Exception("All AI models failed")
                        
                        logger.info(f"AI response length: {len(ai_response)} chars")
                        
                        # Clean up the response - extract JSON
                        if '```json' in ai_response:
                            ai_response = ai_response.split('```json')[1].split('```')[0].strip()
                        elif '```' in ai_response:
                            parts = ai_response.split('```')
                            for part in parts:
                                part = part.strip()
                                if part.startswith('['):
                                    ai_response = part
                                    break
                        
                        # Try to find JSON array in response
                        if not ai_response.startswith('['):
                            # Look for JSON array in the response
                            import re
                            json_match = re.search(r'\[[\s\S]*\]', ai_response)
                            if json_match:
                                ai_response = json_match.group(0)
                        
                        # Parse JSON response
                        extracted_data = json.loads(ai_response)
                        
                        if isinstance(extracted_data, list) and len(extracted_data) > 0:
                            df = pd.DataFrame(extracted_data)
                            logger.info(f"AI successfully extracted {len(df)} items from PDF")
                            logger.info(f"Columns found: {list(df.columns)}")
                            if len(df) > 0:
                                logger.info(f"Sample data: {df.iloc[0].to_dict()}")
                        else:
                            logger.warning("AI returned empty array - no inventory data found in PDF")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="No inventory/product data found in the PDF. Please ensure the PDF contains product information."
                            )
                            
                    except json.JSONDecodeError as je:
                        logger.error(f"Failed to parse AI response as JSON: {je}")
                        logger.error(f"AI response was: {ai_response[:1000]}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Failed to extract structured data from PDF. Please try a different file format."
                        )
                    except HTTPException:
                        raise
                    except Exception as ai_error:
                        logger.error(f"AI extraction failed: {ai_error}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"AI analysis failed: {str(ai_error)}"
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PDF analysis requires AI (Gemini API). Please configure GEMINI_API_KEY."
                    )
                
                if df is None or df.empty:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Could not extract inventory data from PDF."
                    )
                
                logger.info(f"Final PDF extraction: {len(df)} rows, columns: {list(df.columns)}")
                    
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PDF support requires pdfplumber. Install with: pip install pdfplumber"
                )
            except HTTPException:
                raise
            except Exception as pdf_error:
                logger.error(f"PDF parsing error: {pdf_error}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to parse PDF: {str(pdf_error)}"
                )
            
        elif ext in ['.png', '.jpg', '.jpeg']:
            # Image files - would need OCR
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image files require OCR which is not currently supported. Please convert to CSV, JSON, or Excel format."
            )
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract data from file"
            )
        
        # Normalize to OptiStock schema
        df_normalized = normalize_to_schema(df)
        
        # Process the normalized data for proper data types
        df_normalized['SKU'] = df_normalized['SKU'].astype(str)
        df_normalized['Sales_Date'] = pd.to_datetime(df_normalized['Sales_Date'])
        df_normalized['Current_Stock'] = pd.to_numeric(df_normalized['Current_Stock'], errors='coerce').fillna(0).astype(int)
        df_normalized['Cost_Per_Unit'] = pd.to_numeric(df_normalized['Cost_Per_Unit'], errors='coerce').fillna(0)
        df_normalized['Defect_Rate'] = pd.to_numeric(df_normalized['Defect_Rate'], errors='coerce').fillna(0)
        df_normalized['Lead_Time_Days'] = pd.to_numeric(df_normalized['Lead_Time_Days'], errors='coerce').fillna(7).astype(int)
        df_normalized['Quantity_Sold'] = pd.to_numeric(df_normalized['Quantity_Sold'], errors='coerce').fillna(0).astype(int)
        
        # Store in memory cache (this persists during the session)
        global UPLOADED_DATA_CACHE
        UPLOADED_DATA_CACHE[DATA_CACHE_KEY] = df_normalized.copy()
        
        # Also save to CSV as backup
        with csv_write_lock:
            df_normalized.to_csv(DATA_FILE_PATH, index=False)

        # --- Persist in SQLite database ---
        try:
            import sqlite3
            from src.database import DB_PATH
            
            db_conn = sqlite3.connect(DB_PATH)
            db_conn.execute("PRAGMA foreign_keys=OFF")
            db_conn.execute("DELETE FROM daily_sales")
            db_conn.execute("DELETE FROM purchase_orders")
            db_conn.execute("DELETE FROM notifications")
            db_conn.execute("DELETE FROM inventory_items")
            db_conn.commit()
            
            # Insert unique products into inventory_items
            unique_skus = df_normalized.drop_duplicates(subset=['SKU']).copy()
            now_str = datetime.utcnow().isoformat()
            
            for _, row in unique_skus.iterrows():
                # Get selling price (if not in CSV, default to cost * 1.3)
                cost = float(row.get('Cost_Per_Unit', 0.0))
                selling_price = float(row.get('Selling_Price', cost * 1.30)) if 'Selling_Price' in row else cost * 1.30
                
                db_conn.execute("""
                    INSERT INTO inventory_items
                        (sku, product_name, category, current_stock, cost_per_unit,
                         selling_price, supplier, defect_rate, lead_time_days, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(row.get('SKU', '')).upper(),
                    str(row.get('Product_Name', '')),
                    str(row.get('Category', '')),
                    int(row.get('Current_Stock', 0)),
                    cost,
                    round(selling_price, 2),
                    str(row.get('Supplier', '')),
                    float(row.get('Defect_Rate', 0.01)),
                    int(row.get('Lead_Time_Days', 7)),
                    now_str, now_str
                ))
            
            # Insert sales transactions into daily_sales
            for _, row in df_normalized.iterrows():
                s_date = str(row.get('Sales_Date'))[:10]
                if s_date and s_date != 'NaT':
                    db_conn.execute("""
                        INSERT INTO daily_sales (sku, quantity, sale_date, created_at)
                        VALUES (?,?,?,?)
                    """, (
                        str(row.get('SKU', '')).upper(),
                        int(row.get('Quantity_Sold', 0)),
                        s_date,
                        now_str
                    ))
            
            db_conn.execute("PRAGMA foreign_keys=ON")
            db_conn.commit()
            db_conn.close()
            logger.info("✅ Uploaded CSV dataset successfully synced to SQLite database")
        except Exception as sqlite_err:
            logger.error(f"Failed to sync uploaded data to SQLite: {sqlite_err}")
        
        unique_skus = df_normalized['SKU'].nunique()
        logger.info(f"Uploaded {format_detected} file: {len(df_normalized)} records, {unique_skus} unique products")
        logger.info(f"Products: {df_normalized['SKU'].unique().tolist()}")
        
        return {
            "success": True,
            "message": f"Successfully processed {format_detected} file with {unique_skus} products ({len(df_normalized)} total records)",
            "format_detected": format_detected,
            "records_count": len(df_normalized),
            "unique_products": unique_skus,
            "products": df_normalized['SKU'].unique().tolist(),
            "original_columns": list(df.columns),
            "normalized_columns": list(df_normalized.columns)
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON format: {str(e)}"
        )
    except ET.ParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid XML format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}"
        )


# =============================================================================
# SCHEDULED AGENT RUN ENDPOINT (Cloud Scheduler + Pub/Sub)
# =============================================================================

class ScheduledRunResponse(BaseModel):
    """Response model for scheduled agent runs."""
    success: bool
    run_id: str
    trigger: str
    timestamp: str
    products_analyzed: int
    alerts_generated: int
    restock_recommendations: int
    message: str


@app.post("/api/agent/run-daily", response_model=ScheduledRunResponse, tags=["Scheduled"])
async def run_daily_agent(request: Request = None):
    """
    Daily autonomous agent run triggered by Cloud Scheduler via Pub/Sub.
    
    This endpoint:
    1. Validates the Pub/Sub message
    2. Runs analysis on all inventory items
    3. Generates forecasts and risk assessments
    4. Saves results to Firestore
    5. Sends alerts for critical items
    """
    run_start = datetime.now()
    run_id = f"run_{run_start.strftime('%Y%m%d_%H%M%S')}"
    
    # Parse Pub/Sub message if present
    trigger_source = "manual"
    if request:
        try:
            body = await request.json()
            if PUBSUB_HANDLER_AVAILABLE and "message" in body:
                if validate_scheduler_request(body):
                    parsed = parse_pubsub_message(body)
                    trigger_source = "scheduled"
                    logger.info(f"📅 Scheduled run triggered: {parsed.get('message_id', 'unknown')}")
        except Exception:
            pass  # Manual trigger without JSON body
    
    logger.info(f"🚀 Starting daily agent run: {run_id} (trigger: {trigger_source})")
    
    # Load inventory data
    try:
        df = load_supply_chain_data()
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        raise HTTPException(status_code=500, detail="Failed to load inventory data")
    
    # Track results
    products_analyzed = 0
    alerts_generated = 0
    restock_recommendations = 0
    results = []
    
    # Analyze each SKU
    for sku in df['SKU'].unique()[:50]:  # Limit to 50 for cost control
        try:
            inventory = get_inventory_for_sku(df, sku)
            if not inventory:
                continue
            
            # Generate forecast
            try:
                forecast_data = run_demand_forecast(df, sku)
                forecasted_demand = forecast_data.get('forecasted_demand_30_days', 0)
            except Exception:
                forecasted_demand = 0
            
            # Assess risk
            risk = assess_risk(inventory, forecasted_demand)
            
            # Determine decision
            current_stock = inventory.get('current_stock', 0)
            if current_stock < forecasted_demand * 1.2:
                decision = "Restock"
                restock_recommendations += 1
            else:
                decision = "Hold"
            
            products_analyzed += 1
            
            # Save to Firestore if available
            if FIRESTORE_AVAILABLE:
                try:
                    save_forecast(inventory.get('product_name', sku), {
                        "forecasted_demand": forecasted_demand,
                        "current_stock": current_stock,
                        "decision": decision,
                        "risk_level": risk.get('level', 'Unknown'),
                        "risk_score": risk.get('score', 0.5)
                    })
                except Exception as e:
                    logger.error(f"Firestore save failed for {sku}: {e}")
            
            # Generate alerts for critical items
            if risk.get('level') == 'Critical' or (decision == "Restock" and current_stock < 10):
                alerts_generated += 1
                alert_msg = f"CRITICAL: {inventory.get('product_name')} needs immediate restock. Stock: {current_stock}, Demand: {forecasted_demand}"
                
                if FIRESTORE_AVAILABLE:
                    try:
                        save_alert(
                            alert_type="restock_critical",
                            product_name=inventory.get('product_name', sku),
                            message=alert_msg,
                            severity="critical"
                        )
                    except Exception:
                        pass
                
                logger.warning(f"🚨 {alert_msg}")
            
            results.append({
                "sku": sku,
                "decision": decision,
                "risk_level": risk.get('level', 'Unknown')
            })
            
        except Exception as e:
            logger.error(f"Analysis failed for SKU {sku}: {e}")
            continue
    
    # Log the run
    run_duration = (datetime.now() - run_start).total_seconds()
    run_log = {
        "run_id": run_id,
        "trigger": trigger_source,
        "products_analyzed": products_analyzed,
        "alerts_generated": alerts_generated,
        "restock_recommendations": restock_recommendations,
        "duration_seconds": run_duration,
        "status": "completed"
    }
    
    if FIRESTORE_AVAILABLE:
        try:
            log_agent_run(run_log)
        except Exception as e:
            logger.error(f"Failed to log run: {e}")
    
    logger.info(f"✅ Daily run completed: {products_analyzed} analyzed, {restock_recommendations} restock, {alerts_generated} alerts in {run_duration:.2f}s")
    
    return ScheduledRunResponse(
        success=True,
        run_id=run_id,
        trigger=trigger_source,
        timestamp=run_start.isoformat(),
        products_analyzed=products_analyzed,
        alerts_generated=alerts_generated,
        restock_recommendations=restock_recommendations,
        message=f"Agent run completed successfully in {run_duration:.2f} seconds"
    )


@app.get("/api/agent/run-history", tags=["Scheduled"])
async def get_run_history(limit: int = 30):
    """Get history of scheduled agent runs."""
    if not FIRESTORE_AVAILABLE:
        return {
            "runs": [],
            "message": "Firestore not available - no history in local mode"
        }
    
    try:
        runs = get_agent_run_history(limit)
        return {"runs": runs, "total": len(runs)}
    except Exception as e:
        logger.error(f"Failed to get run history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/cloud-status", tags=["System"])
async def get_cloud_status():
    """Get status of cloud services (Firestore, Pub/Sub, etc.)."""
    status_info = {
        "environment": os.environ.get("K_SERVICE", "local"),
        "revision": os.environ.get("K_REVISION", "local"),
        "region": os.environ.get("GOOGLE_CLOUD_REGION", "unknown"),
        "firestore": {
            "available": FIRESTORE_AVAILABLE,
            "status": "unknown"
        },
        "gemini_ai": {
            "available": GENAI_AVAILABLE,
            "status": "configured" if GENAI_AVAILABLE else "not_configured"
        },
        "pubsub_handler": {
            "available": PUBSUB_HANDLER_AVAILABLE
        }
    }
    
    # Check Firestore health
    if FIRESTORE_AVAILABLE:
        try:
            fs_health = firestore_health_check()
            status_info["firestore"]["status"] = fs_health.get("status", "unknown")
            status_info["firestore"]["project"] = fs_health.get("project", "unknown")
        except Exception as e:
            status_info["firestore"]["status"] = "error"
            status_info["firestore"]["error"] = str(e)
    
    return status_info


# =============================================================================
# VOICE ASSISTANT CHAT ENDPOINT
# =============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    language: str = "en"

@app.post("/api/chat", tags=["Voice Assistant"])
async def chat_endpoint(request: ChatRequest):
    """
    AI-powered chat endpoint for voice assistant.
    Accepts natural language queries about inventory and returns AI responses.
    Supports multilingual responses (en, ta, hi).
    """
    try:
        # Get inventory data for context
        df = load_supply_chain_data()
        
        # Prepare inventory summary
        total_products = len(df['SKU'].unique()) if not df.empty else 0
        
        # Get low stock items
        low_stock_items = []
        if not df.empty:
            grouped = df.groupby('SKU').agg({
                'Product_Name': 'first',
                'Current_Stock': 'first',
                'Lead_Time_Days': 'first'
            }).reset_index()
            for _, row in grouped.iterrows():
                if row['Current_Stock'] < 50:  # Simple threshold
                    low_stock_items.append(f"{row['Product_Name']} ({row['Current_Stock']} units)")
        
        # Rule-based responses for common queries
        query_lower = request.message.lower()
        
        # Check for low stock queries
        if any(word in query_lower for word in ['low', 'stock', 'shortage', 'running out', 'critical', 'attention']):
            if low_stock_items:
                response = f"Items with low stock: {', '.join(low_stock_items[:5])}."
            else:
                response = "All items have sufficient stock levels."
        
        # Check for inventory/product count queries
        elif any(word in query_lower for word in ['how many', 'total', 'products', 'items', 'inventory']):
            response = f"You have {total_products} unique products in your inventory."
        
        # Check for greeting
        elif any(word in query_lower for word in ['hello', 'hi', 'hey', 'good morning', 'good evening']):
            response = "Hello! I'm your OptiStock assistant. Ask me about inventory, low stock items, or sales!"
        
        # Check for help
        elif any(word in query_lower for word in ['help', 'what can you do', 'features']):
            response = "I can help you check inventory levels, find low stock items, and get product information. Try asking 'What items are low on stock?'"
        
        # Try AI if available
        elif GENAI_AVAILABLE:
            try:
                inventory_summary = f"Total products: {total_products}. Low stock items: {len(low_stock_items)}."
                prompt = f"""You are OptiStock Assistant for inventory management.
Context: {inventory_summary}
User: {request.message}
Give a brief, helpful response (1-2 sentences):"""
                
                model = genai.GenerativeModel('gemini-1.5-flash')
                ai_response = model.generate_content(prompt)
                response = ai_response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini API error: {e}")
                response = f"I have {total_products} products tracked. {len(low_stock_items)} items may need attention. What would you like to know?"
        else:
            response = f"I have {total_products} products tracked. {len(low_stock_items)} items may need attention. What would you like to know?"
        
        return {
            "response": response,
            "language": request.language
        }
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return {
            "response": "Sorry, I couldn't process your request. Please try again.",
            "language": request.language
        }


# =============================================================================
# RUN CONFIGURATION
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
