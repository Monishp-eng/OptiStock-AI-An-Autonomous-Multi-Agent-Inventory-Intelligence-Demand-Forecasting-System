# src/agent_logic.py
"""
OptiStock: Gemini AI Integration for MSME-Friendly Inventory Analysis.

Provides plain-language inventory insights tailored for small shop owners.
The Gemini prompt is designed to avoid jargon and act as a
"Business Consultant for a small shop owner."
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini API Configuration
# ---------------------------------------------------------------------------
try:
    import google.generativeai as genai

    _api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if _api_key:
        genai.configure(api_key=_api_key)
        GENAI_AVAILABLE = True
    else:
        GENAI_AVAILABLE = False
        logger.warning("GOOGLE_API_KEY not set — Gemini AI features disabled")
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    logger.warning("google-generativeai not installed — Gemini AI features disabled")


def get_gemini_model(model_name: str = "gemini-1.5-flash"):
    """Return a Gemini GenerativeModel instance (or None if unavailable)."""
    if not GENAI_AVAILABLE:
        return None
    return genai.GenerativeModel(model_name)


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def gemini_analyze_sku(sku_data: dict, forecast_data: dict) -> dict:
    """
    Use Gemini to produce an MSME-friendly analysis for one SKU.

    Parameters
    ----------
    sku_data : dict
        Keys expected: sku, product_name, category, current_stock,
        cost_per_unit, supplier, defect_rate, lead_time_days,
        avg_daily_sales, days_of_stock.
    forecast_data : dict
        Keys expected: sku, forecasted_demand_30_days, plot_data.

    Returns
    -------
    dict with exactly three keys:
        explanation      – 2-3 plain-language sentences about the situation
        reorderUrgency   – one of Critical | High | Medium | Low | None
        recommendation   – 1-2 actionable sentences for the shop owner
    """
    current_stock = sku_data.get("current_stock", 0)
    avg_daily_sales = sku_data.get("avg_daily_sales", 0)
    days_of_stock = sku_data.get("days_of_stock", 0)
    forecasted_demand = forecast_data.get("forecasted_demand_30_days", 0)
    lead_time = sku_data.get("lead_time_days", 7)
    product_name = sku_data.get("product_name", sku_data.get("sku", "Unknown"))
    supplier = sku_data.get("supplier", "Unknown")
    cost = sku_data.get("cost_per_unit", 0)

    # ---- Build the Gemini prompt ------------------------------------------
    prompt = f"""You are a **Business Consultant for a small shop owner** in India.
The shop owner is NOT tech-savvy. Speak in simple, everyday language.
Avoid inventory jargon like "safety stock", "EOQ", "lead time variance",
"reorder point", or "service level". Instead, use phrases a shopkeeper
would naturally understand.

Here is the data for one product in the shop:

Product         : {product_name}
Current Stock   : {current_stock} units
Avg Daily Sales : {round(avg_daily_sales, 1)} units/day
Days of Stock   : {round(days_of_stock, 1)} days (how long current stock will last)
30-Day Forecast : {forecasted_demand} units expected to sell in the next month
Supplier        : {supplier}
Delivery Time   : {lead_time} days (time for new stock to arrive after ordering)
Unit Cost       : ₹{cost}

Based on this, reply ONLY with a valid JSON object (no markdown fences,
no extra text) containing exactly these three keys:

{{
  "explanation": "<2-3 sentences explaining the stock situation in plain language, as if talking to the shop owner face-to-face>",
  "reorderUrgency": "<one of: Critical, High, Medium, Low, None>",
  "recommendation": "<1-2 actionable sentences telling the shop owner exactly what to do next and why>"
}}

Urgency guidelines:
- Critical : days_of_stock < delivery time — the shop may run out before new stock arrives.
- High     : days_of_stock < delivery time × 2 — stock is getting tight.
- Medium   : stock covers 2-4 weeks but an order should be planned.
- Low      : stock is healthy for now.
- None     : stock is much higher than needed; no ordering required.

Rules:
- Always mention how many days of stock are left in the explanation.
- If restocking is needed, suggest a rough quantity to order in the recommendation.
- If stock is excessive, recommend holding off on purchases to save cash.
"""

    # ---- Call Gemini ------------------------------------------------------
    model = get_gemini_model()
    if model is None:
        return _fallback_analysis(sku_data, forecast_data)

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Strip markdown code fences if Gemini wraps them anyway
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        # Validate required keys
        for key in ("explanation", "reorderUrgency", "recommendation"):
            if key not in result:
                raise KeyError(f"Missing key in Gemini response: {key}")

        return result

    except Exception as e:
        logger.error(f"Gemini analysis failed for {sku_data.get('sku')}: {e}")
        return _fallback_analysis(sku_data, forecast_data)


# ---------------------------------------------------------------------------
# Rule-based fallback (when Gemini is unavailable or errors out)
# ---------------------------------------------------------------------------

def _fallback_analysis(sku_data: dict, forecast_data: dict) -> dict:
    """Deterministic fallback that mirrors Gemini output structure."""
    current_stock = sku_data.get("current_stock", 0)
    avg_daily_sales = sku_data.get("avg_daily_sales", 0)
    days_of_stock = sku_data.get("days_of_stock", 0)
    forecasted_demand = forecast_data.get("forecasted_demand_30_days", 0)
    lead_time = sku_data.get("lead_time_days", 7)
    product_name = sku_data.get("product_name", "This product")

    # No sales data
    if days_of_stock <= 0 or avg_daily_sales <= 0:
        return {
            "explanation": (
                f"{product_name} has no recent sales recorded. "
                "It may be a new product or a seasonal item that hasn't started selling yet."
            ),
            "reorderUrgency": "Low",
            "recommendation": (
                "Check if this product is still relevant to your customers "
                "before spending money on more stock."
            ),
        }

    # Critical — will run out before delivery arrives
    if days_of_stock < lead_time:
        order_qty = max(int(lead_time * 2 * avg_daily_sales - current_stock), 1)
        return {
            "explanation": (
                f"You only have about {int(days_of_stock)} days of {product_name} left, "
                f"but it takes {lead_time} days for new stock to arrive. "
                "You could run out before the delivery comes."
            ),
            "reorderUrgency": "Critical",
            "recommendation": (
                f"Order around {order_qty} units right away from your supplier. "
                "This should cover you while you wait for delivery plus a little extra buffer."
            ),
        }

    # High — tight but not immediate
    if days_of_stock < lead_time * 2:
        order_qty = max(int(forecasted_demand - current_stock + lead_time * avg_daily_sales), 1)
        return {
            "explanation": (
                f"{product_name} has about {int(days_of_stock)} days of stock remaining. "
                "It's not urgent yet, but you should plan your next order soon."
            ),
            "reorderUrgency": "High",
            "recommendation": (
                f"Place an order for roughly {order_qty} units within the next few days "
                "so you don't run low."
            ),
        }

    # Overstock
    if current_stock > forecasted_demand * 2:
        return {
            "explanation": (
                f"You have plenty of {product_name} — about {int(days_of_stock)} days' worth. "
                "Your stock is more than double what you're expected to sell in a month."
            ),
            "reorderUrgency": "None",
            "recommendation": (
                "No need to order more right now. Hold off on purchasing to free up "
                "your cash for products that actually need restocking."
            ),
        }

    # Healthy
    return {
        "explanation": (
            f"{product_name} has roughly {int(days_of_stock)} days of stock. "
            "Sales are steady and stock levels look healthy."
        ),
        "reorderUrgency": "Low",
        "recommendation": (
            "You're in good shape. Keep an eye on sales and reorder when stock "
            "drops below about two weeks of supply."
        ),
    }
