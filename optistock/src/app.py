#-*- coding: utf-8 -*-
"""
OptiStock: Autonomous Procurement Agent (ADK Version)
Main application file using the Google Agent Development Kit (ADK).
This version is hardened for production-readiness.
"""

# --- Core Imports ---
import logging
import os
import re
import json
from typing import List, Dict, Any, Optional

# --- Library Imports ---
import pandas as pd
import streamlit as st
from prophet import Prophet

# --- Google Cloud & Vertex AI Imports ---
import vertexai
from vertexai.generative_models import GenerativeModel

# --- Google Agent Development Kit (ADK) Imports ---
# NOTE: The 'google-adk' library is a requirement for this project to run.
# The following code block provides a mock implementation for local testing
# if the library is not installed. In a real production environment, you would
# `pip install google-adk` and this block would not be needed.
try:
    import google_adk as adk
    ADK_INSTALLED = True
except ImportError:
    ADK_INSTALLED = False
    st.warning("`google_adk` library not found. Using mock objects for demonstration. The core agent logic will be simulated.")
    class MockAdk:
        def tool(self, func):
            # In a real ADK, this would register the function with its schema
            return func
        class Agent:
            def __init__(self, model, tools, system_prompt):
                self._system_prompt = system_prompt
            def chat_session(self):
                # Returns a mock session object
                return MockAdk.Session(self._system_prompt)
        class Session:
            def __init__(self, system_prompt):
                 self._prompt = system_prompt
            def send(self, prompt: str) -> str:
                # This mock simulates a final agent response without actual tool use.
                sku_match = re.search(r'SKU-\d+', prompt)
                sku = sku_match.group(0) if sku_match else "SKU-UNKNOWN"
                mock_response = {
                    "sku": sku,
                    "decision": "Mock Decision: Proceed with procurement.",
                    "reasoning": "This is a simulated response because the Google ADK is not installed. The agent would normally use tools to get inventory data, run a forecast, and assess risk before making this decision.",
                    "email_draft": {
                        "subject": f"Simulated Procurement for {sku}",
                        "body": "This is a placeholder email. In a real run, Gemini would generate a detailed negotiation email here."
                    }
                }
                return json.dumps(mock_response, indent=2)
    adk = MockAdk()

# --- Mermaid Diagram of Agent Architecture ---
MERMAID_DIAGRAM = """
graph TD
    A[Start Daily Cycle] --> B{For each SKU};
    B --> C[ADK Agent Session];
    C -- "Analyze SKU" --> D{ReAct Loop - Managed by ADK};
    D -- Needs Data --> E[Tool Call: get_inventory_status];
    D -- Needs Forecast --> F[Tool Call: predict_demand_ml];
    D -- Needs Risk Score --> G[Tool Call: assess_supply_risk];
    D -- Needs Email --> H[Tool Call: draft_negotiation_email];
    E --> D; F --> D; G --> D; H --> D;
    D -- Analysis Complete --> I[Agent provides Final Summary];
    I --> B;
"""

# --- Logging and Page Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
st.set_page_config(page_title="OptiStock ADK Agent", layout="wide")
st.title("🤖 OptiStock: Procurement Agent (Powered by ADK)")
st.markdown("An autonomous agent using the **Google Agent Development Kit (ADK)**, Gemini 1.5 Pro, and on-the-fly ML forecasting.")

# --- Vertex AI Initialization ---
try:
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not PROJECT_ID:
        st.error("🚨 `GOOGLE_CLOUD_PROJECT` environment variable is not set.")
        st.stop()
    LOCATION = "us-central1"
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel("gemini-1.5-pro-001")
except Exception as e:
    st.error(f"🚨 Vertex AI Initialization Failed: {e}")
    st.stop()

# --- Data Loading ---
@st.cache_data
def load_data(filepath: str = "data/supply_chain_data.csv") -> Optional[pd.DataFrame]:
    """Loads and preprocesses the supply chain data."""
    try:
        df = pd.read_csv(filepath)
        df['Sales_Date'] = pd.to_datetime(df['Sales_Date'])
        return df
    except FileNotFoundError:
        st.error(f"🚨 Data file not found: `{filepath}`.")
        return None

supply_chain_df = load_data()


# --- ADK Tool Definitions ---
@adk.tool
def get_inventory_status(sku: str) -> List[Dict[str, Any]]:
    """Gets current inventory status for a given SKU."""
    if supply_chain_df is None: return [{"error": "Dataframe not loaded."}]
    data = supply_chain_df[supply_chain_df['SKU'].str.lower() == sku.lower()]
    if data.empty: return [{"error": f"Product with SKU '{sku}' not found."}]
    rec = data.iloc[0]
    return [{"sku": rec['SKU'], "product_name": rec['Product_Name'], "current_stock": int(rec['Current_Stock']), "cost_per_unit": float(rec['Cost_Per_Unit']), "supplier": rec['Supplier'], "defect_rate": float(rec['Defect_Rate']), "lead_time_days": int(rec['Lead_Time_Days'])}]

@adk.tool
def predict_demand_ml(sku: str) -> List[Dict[str, Any]]:
    """Trains a Prophet model on-the-fly to forecast demand for an SKU."""
    if supply_chain_df is None: return [{"error": "Dataframe not loaded."}]
    logging.info(f"Starting demand forecast for SKU: {sku}")
    history = supply_chain_df[supply_chain_df['SKU'] == sku][['Sales_Date', 'Quantity_Sold']].rename(columns={'Sales_Date': 'ds', 'Quantity_Sold': 'y'})
    if history.empty: return [{"error": f"No sales history for SKU {sku}."}]
    try:
        m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
        m.fit(history)
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        total_forecast = int(forecast.iloc[-30:]['yhat'].sum())
        logging.info(f"Forecast for {sku} (30 days): {total_forecast} units.")
        return [{"sku": sku, "forecasted_demand_30_days": total_forecast}]
    except Exception as e:
        logging.error(f"Prophet model failed for SKU {sku}: {e}")
        return [{"error": str(e)}]

@adk.tool
def assess_supply_risk(defect_rate: float, lead_time_days: int) -> List[Dict[str, Any]]:
    """Computes a risk score for a supplier."""
    risk_score = (defect_rate * 100) * 2 + (lead_time_days / 7)
    level = "High" if risk_score > 10 else "Medium" if risk_score > 5 else "Low"
    return [{"risk_score": round(risk_score, 2), "risk_level": level}]

@adk.tool
def draft_negotiation_email(product_name: str, supplier_name: str, required_units: int, reason: str) -> List[Dict[str, Any]]:
    """Drafts a professional negotiation email to a supplier."""
    prompt = f"""Draft a professional procurement email.
    **Product:** {product_name}
    **Supplier:** {supplier_name}
    **Reason:** {reason}
    **Units Required:** {required_units}
    **Instructions:** Be polite. If it's a bulk order, ask for a 10% discount. Always request a quote and lead time. Format as: Subject: [Subject]\n\n[Body]"""
    try:
        response = model.generate_content(prompt)
        email_text = response.text
        subject = email_text.split("Subject:")[1].split("\n\n")[0].strip()
        body = email_text.split("\n\n", 1)[1].strip()
        return [{"subject": subject, "body": body}]
    except Exception as e:
        return [{"error": f"Failed to draft email: {e}"}]

# --- ADK Agent Definition ---
SYSTEM_PROMPT = """
You are OptiStock, an autonomous procurement agent. Your goal is to analyze product inventory, identify risks, and decide on actions.
For any given SKU, your process is:
1. Get inventory status.
2. If stock is low, forecast demand. A safety buffer is 20% of the forecast.
3. If `forecasted_demand * 1.2 > current_stock`, it's a stockout risk.
4. Independently, assess supplier risk.
5. Based on all data, decide. If stockout risk exists, you MUST draft a negotiation email.
6. Conclude with a final, clean JSON summary containing `sku`, `decision`, `reasoning`, and an optional `email_draft`.
"""

optistock_agent = adk.Agent(
    model=model,
    tools=[get_inventory_status, predict_demand_ml, assess_supply_risk, draft_negotiation_email],
    system_prompt=SYSTEM_PROMPT
) if ADK_INSTALLED else adk.Agent(None, [], "")

# --- Main Orchestration Logic ---
def run_autonomous_cycle(skus_to_analyze: List[str]):
    """Iterates through SKUs and uses the ADK agent to perform analysis."""
    st.header("AGENT CYCLE IN PROGRESS...")
    progress_bar = st.progress(0, text="Starting agent cycle...")
    results = []
    
    with st.container(height=400, border=False):
        for i, sku in enumerate(skus_to_analyze):
            st.write(f"▶️ **Analyzing SKU: {sku}**")
            agent_session = optistock_agent.chat_session()
            initial_prompt = f"Analyze the procurement status for SKU {sku} and provide your final JSON summary."
            final_response = agent_session.send(initial_prompt)
            st.write(f"✅ **Agent decision for {sku} received.**")
            results.append({"sku": sku, "summary": final_response})
            progress_bar.progress((i + 1) / len(skus_to_analyze), text=f"Analyzed {sku}")
            
    st.session_state.agent_results = results
    st.header("✅ Agent Cycle Complete")

# --- Streamlit UI Main Body ---
if supply_chain_df is not None:
    if st.button("🚀 Run Daily Autonomous Cycle", type="primary", use_container_width=True):
        # This is now dynamic and runs on all products in the dataset.
        skus = supply_chain_df['SKU'].unique().tolist()
        run_autonomous_cycle(skus)

    if 'agent_results' in st.session_state:
        st.divider()
        st.header("📊 Agent Analysis Results")
        for result in st.session_state.agent_results:
            with st.expander(f"**{result['sku']}** - Analysis Summary", expanded=True):
                try:
                    # More robust parsing: remove markdown and load as JSON.
                    clean_summary = re.sub(r'```json\n|```', '', result['summary']).strip()
                    summary_dict = json.loads(clean_summary)
                    
                    st.success(f"**Decision:** {summary_dict.get('decision', 'N/A')}")
                    st.write(f"**Reasoning:** {summary_dict.get('reasoning', 'N/A')}")
                    if 'email_draft' in summary_dict and summary_dict['email_draft']:
                        email = summary_dict['email_draft'][0] if isinstance(summary_dict['email_draft'], list) else summary_dict['email_draft']
                        st.text_input("Email Subject", value=email.get('subject'), key=f"subject_{result['sku']}", disabled=True)
                        st.text_area("Email Body", value=email.get('body'), key=f"body_{result['sku']}", height=250)
                except (json.JSONDecodeError, TypeError, AttributeError) as e:
                    st.warning(f"Could not parse agent's JSON summary (Error: {e}). Displaying raw output:")
                    st.code(result['summary'], language='text')

    st.divider()
    st.header("📦 Live Supply Chain Data")
    st.dataframe(supply_chain_df)
    with st.expander("View Agent Architecture Diagram"):
        st.graphviz_chart(MERMAID_DIAGRAM.replace("graph TD", "digraph"))
else:
    st.warning("Could not load supply chain data. The application cannot proceed.")