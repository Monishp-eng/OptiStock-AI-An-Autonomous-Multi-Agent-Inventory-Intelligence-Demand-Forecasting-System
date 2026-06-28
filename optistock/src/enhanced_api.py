# src/enhanced_api.py
"""
OptiStock: Enhanced API Endpoints
New endpoints for advanced AI features, NL queries, and reporting.
"""

from fastapi import APIRouter, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create router for enhanced features
router = APIRouter(prefix="/api/v2", tags=["Enhanced AI"])


# =============================================================================
# PYDANTIC MODELS FOR ENHANCED ENDPOINTS
# =============================================================================

class NLQueryRequest(BaseModel):
    """Natural language query request."""
    query: str = Field(..., description="Natural language question about inventory")
    include_analytics: bool = Field(True, description="Include analytics context")


class NLQueryResponse(BaseModel):
    """Natural language query response."""
    success: bool
    query: str
    intent: str
    response: str
    products_mentioned: List[str] = []
    suggested_actions: List[str] = []
    ai_powered: bool = False


class EnhancedAnalysisRequest(BaseModel):
    """Request for enhanced SKU analysis."""
    sku: str
    include_forecast: bool = True
    include_optimization: bool = True
    include_supplier_score: bool = True
    include_explanation: bool = True


class EnhancedAnalysisResponse(BaseModel):
    """Complete enhanced analysis response."""
    sku: str
    product_name: str
    
    # Current status
    current_stock: int
    stock_status: str
    status_reason: str
    
    # Forecast
    forecasted_demand_30_days: int
    forecast_confidence: float
    forecast_plot_data: List[Dict] = []
    
    # Optimization metrics
    safety_stock: int
    reorder_point: int
    economic_order_quantity: int
    days_of_supply: float
    
    # Supplier info
    supplier_name: str
    supplier_reliability_score: Optional[float] = None
    supplier_risk_level: Optional[str] = None
    
    # Decision
    decision: str
    decision_title: str
    confidence_score: float
    units_to_order: int
    order_urgency: str
    
    # Explanations
    explanation_summary: str
    primary_factors: List[Dict] = []
    risk_factors: List[str] = []
    alternative_actions: List[Dict] = []
    
    # Email draft (if restock needed)
    email_draft: Optional[Dict] = None


class ReportRequest(BaseModel):
    """Report generation request."""
    report_type: str = Field(..., description="'executive_summary', 'procurement', 'email'")
    period: str = Field("weekly", description="'weekly' or 'monthly'")
    sku: Optional[str] = None
    email_type: Optional[str] = None
    email_context: Optional[Dict] = None


class SupplierScoreRequest(BaseModel):
    """Supplier scoring request."""
    supplier_name: str
    defect_rate: float = Field(0.01, ge=0, le=1)
    lead_time_days: int = Field(7, ge=1)
    on_time_rate: float = Field(0.9, ge=0, le=1)
    unit_cost: float = Field(100, gt=0)
    market_avg_cost: float = Field(100, gt=0)


class BatchAnalysisResponse(BaseModel):
    """Batch analysis summary."""
    total_analyzed: int
    restock_urgent: int
    restock_soon: int
    healthy: int
    overstock: int
    total_order_value: float
    results: List[Dict]


# =============================================================================
# IMPORT ENHANCED MODULES
# =============================================================================

def get_modules():
    """Lazy import of enhanced modules."""
    modules = {}
    
    try:
        from src.advanced_forecasting import HybridDemandForecaster, run_hybrid_forecast
        modules['forecasting'] = {
            'HybridDemandForecaster': HybridDemandForecaster,
            'run_hybrid_forecast': run_hybrid_forecast
        }
    except ImportError as e:
        logger.warning(f"Advanced forecasting not available: {e}")
    
    try:
        from src.inventory_optimizer import InventoryOptimizer, analyze_inventory_item
        modules['optimizer'] = {
            'InventoryOptimizer': InventoryOptimizer,
            'analyze_inventory_item': analyze_inventory_item
        }
    except ImportError as e:
        logger.warning(f"Inventory optimizer not available: {e}")
    
    try:
        from src.supplier_scoring import SupplierReliabilityScorer, score_supplier
        modules['supplier'] = {
            'SupplierReliabilityScorer': SupplierReliabilityScorer,
            'score_supplier': score_supplier
        }
    except ImportError as e:
        logger.warning(f"Supplier scoring not available: {e}")
    
    try:
        from src.xai_engine import ExplainableDecisionEngine, generate_explanation
        modules['xai'] = {
            'ExplainableDecisionEngine': ExplainableDecisionEngine,
            'generate_explanation': generate_explanation
        }
    except ImportError as e:
        logger.warning(f"XAI engine not available: {e}")
    
    try:
        from src.nl_query_engine import NaturalLanguageQueryEngine, query_inventory
        modules['nlq'] = {
            'NaturalLanguageQueryEngine': NaturalLanguageQueryEngine,
            'query_inventory': query_inventory
        }
    except ImportError as e:
        logger.warning(f"NL query engine not available: {e}")
    
    try:
        from src.report_generator import IntelligentReportGenerator, generate_report
        modules['reports'] = {
            'IntelligentReportGenerator': IntelligentReportGenerator,
            'generate_report': generate_report
        }
    except ImportError as e:
        logger.warning(f"Report generator not available: {e}")
    
    return modules


# =============================================================================
# ENHANCED ENDPOINTS
# =============================================================================

@router.get("/health", tags=["System"])
async def enhanced_health_check():
    """Check health of enhanced modules."""
    modules = get_modules()
    
    # Check Gemini AI availability from agent_logic
    try:
        from src.agent_logic import GENAI_AVAILABLE
        gemini_available = GENAI_AVAILABLE
    except ImportError:
        gemini_available = False
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "gemini_ai_available": gemini_available,
        "enhanced_modules": {
            "advanced_forecasting": "forecasting" in modules,
            "inventory_optimizer": "optimizer" in modules,
            "supplier_scoring": "supplier" in modules,
            "xai_engine": "xai" in modules,
            "nl_query_engine": "nlq" in modules,
            "report_generator": "reports" in modules
        }
    }


@router.post("/query", response_model=NLQueryResponse, tags=["Natural Language"])
async def natural_language_query(request: NLQueryRequest):
    """
    Process natural language query about inventory.
    
    Example queries:
    - "Which products will face stockout next week?"
    - "Show me slow-moving items"
    - "What should I order this week?"
    - "Give me an executive summary"
    """
    modules = get_modules()
    
    if 'nlq' not in modules:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Natural language query module not available"
        )
    
    # Get inventory data
    try:
        from src.api import load_supply_chain_data
        df = load_supply_chain_data()
        
        # Convert to list of dicts
        inventory_data = []
        for sku in df['SKU'].unique():
            sku_data = df[df['SKU'] == sku].iloc[0]
            inventory_data.append({
                'sku': str(sku_data['SKU']),
                'product_name': str(sku_data['Product_Name']),
                'category': str(sku_data['Category']),
                'current_stock': int(sku_data['Current_Stock']),
                'cost_per_unit': float(sku_data['Cost_Per_Unit']),
                'supplier': str(sku_data['Supplier']),
                'defect_rate': float(sku_data['Defect_Rate']),
                'lead_time_days': int(sku_data['Lead_Time_Days'])
            })
    except Exception as e:
        logger.error(f"Failed to load inventory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load inventory data: {str(e)}"
        )
    
    # Process query
    engine = modules['nlq']['NaturalLanguageQueryEngine']()
    result = await engine.process_query(request.query, inventory_data)
    
    return NLQueryResponse(**result)


@router.post("/analyze/{sku}", tags=["Enhanced Analysis"])
async def enhanced_sku_analysis(
    sku: str,
    include_forecast: bool = Query(True, description="Include demand forecast"),
    include_optimization: bool = Query(True, description="Include inventory optimization"),
    include_supplier: bool = Query(True, description="Include supplier scoring"),
    include_explanation: bool = Query(True, description="Include XAI explanation")
) -> Dict:
    """
    Run comprehensive enhanced analysis for a specific SKU.
    
    Includes:
    - Hybrid demand forecasting (Prophet + XGBoost)
    - Dynamic safety stock and reorder point
    - Supplier reliability scoring
    - Explainable AI decision with factors
    """
    modules = get_modules()
    
    try:
        from src.api import load_supply_chain_data
        import pandas as pd
        
        df = load_supply_chain_data()
        
        # Get SKU data
        sku_df = df[df['SKU'].str.upper() == sku.upper()]
        if sku_df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found"
            )
        
        sku_data = sku_df.iloc[0]
        current_stock = int(sku_data['Current_Stock'])
        unit_cost = float(sku_data['Cost_Per_Unit'])
        lead_time = int(sku_data['Lead_Time_Days'])
        defect_rate = float(sku_data['Defect_Rate'])
        supplier_name = str(sku_data['Supplier'])
        product_name = str(sku_data['Product_Name'])
        
        # Get sales history
        sales_df = df[df['SKU'] == sku][['Sales_Date', 'Quantity_Sold']].copy()
        sales_df = sales_df.rename(columns={'Sales_Date': 'ds', 'Quantity_Sold': 'y'})
        sales_df['ds'] = pd.to_datetime(sales_df['ds'])
        sales_df = sales_df.sort_values('ds')
        
        daily_demands = sales_df['y'].tolist() if not sales_df.empty else [current_stock * 0.03] * 30
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data loading failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    
    result = {
        'sku': sku,
        'product_name': product_name,
        'current_stock': current_stock,
        'supplier_name': supplier_name,
        'analysis_timestamp': datetime.now().isoformat()
    }
    
    # Run forecast
    forecasted_demand = int(sum(daily_demands[-30:]) if len(daily_demands) >= 30 else sum(daily_demands))
    forecast_confidence = 0.85
    forecast_plot_data = []
    
    if include_forecast and 'forecasting' in modules and len(sales_df) >= 7:
        try:
            forecast_result = modules['forecasting']['run_hybrid_forecast'](
                sales_df, sku, forecast_days=30
            )
            if forecast_result.get('success'):
                forecasted_demand = forecast_result.get('forecasted_demand_30_days', forecasted_demand)
                forecast_confidence = forecast_result.get('model_metrics', {}).get('confidence_score', 0.85)
                forecast_plot_data = forecast_result.get('daily_forecast', [])
                result['forecast_details'] = {
                    'confidence_interval': forecast_result.get('confidence_interval', {}),
                    'anomalies_detected': forecast_result.get('anomalies_detected', []),
                    'explainability': forecast_result.get('explainability', {})
                }
        except Exception as e:
            logger.warning(f"Forecast failed for {sku}: {e}")
    
    result['forecasted_demand_30_days'] = forecasted_demand
    result['forecast_confidence'] = forecast_confidence
    result['forecast_plot_data'] = forecast_plot_data
    
    # Run optimization
    safety_stock = int(forecasted_demand * 0.2)
    reorder_point = int(forecasted_demand * 0.4)
    eoq = int(forecasted_demand * 0.5)
    days_of_supply = (current_stock / (forecasted_demand / 30)) if forecasted_demand > 0 else 999
    stock_status = "healthy"
    status_reason = "Stock levels optimal"
    units_to_order = 0
    order_urgency = "not_needed"
    
    if include_optimization and 'optimizer' in modules:
        try:
            opt_result = modules['optimizer']['analyze_inventory_item'](
                sku=sku,
                product_name=product_name,
                current_stock=current_stock,
                daily_demands=daily_demands,
                lead_time_days=lead_time,
                unit_cost=unit_cost,
                service_level=0.95
            )
            if opt_result.get('success'):
                safety_stock = opt_result.get('safety_stock', safety_stock)
                reorder_point = opt_result.get('reorder_point', reorder_point)
                eoq = opt_result.get('economic_order_quantity', eoq)
                days_of_supply = opt_result.get('days_of_supply', days_of_supply)
                stock_status = opt_result.get('stock_status', stock_status)
                status_reason = opt_result.get('status_reason', status_reason)
                units_to_order = opt_result.get('units_to_order', 0)
                order_urgency = opt_result.get('order_urgency', 'not_needed')
                
                result['optimization_details'] = {
                    'safety_stock_explanation': opt_result.get('safety_stock_explanation', {}),
                    'reorder_point_explanation': opt_result.get('reorder_point_explanation', {}),
                    'eoq_explanation': opt_result.get('eoq_explanation', {}),
                    'inventory_turnover': opt_result.get('inventory_turnover', 0),
                    'stockout_probability': opt_result.get('stockout_probability', 0),
                    'holding_cost_daily': opt_result.get('holding_cost_daily', 0)
                }
        except Exception as e:
            logger.warning(f"Optimization failed for {sku}: {e}")
    
    result.update({
        'safety_stock': safety_stock,
        'reorder_point': reorder_point,
        'economic_order_quantity': eoq,
        'days_of_supply': round(days_of_supply, 1),
        'stock_status': stock_status,
        'status_reason': status_reason,
        'units_to_order': units_to_order,
        'order_urgency': order_urgency
    })
    
    # Supplier scoring
    supplier_score = None
    supplier_risk = None
    
    if include_supplier and 'supplier' in modules:
        try:
            supplier_result = modules['supplier']['score_supplier'](
                supplier_name=supplier_name,
                defect_rate=defect_rate,
                lead_time_days=lead_time,
                unit_cost=unit_cost
            )
            if supplier_result.get('success'):
                supplier_score = supplier_result.get('reliability_score')
                supplier_risk = supplier_result.get('risk_level')
                result['supplier_details'] = {
                    'overall_grade': supplier_result.get('overall_grade'),
                    'delivery_score': supplier_result.get('delivery_score'),
                    'quality_score': supplier_result.get('quality_score'),
                    'recommendations': supplier_result.get('recommendations', [])
                }
        except Exception as e:
            logger.warning(f"Supplier scoring failed: {e}")
    
    result['supplier_reliability_score'] = supplier_score
    result['supplier_risk_level'] = supplier_risk
    
    # XAI Explanation
    decision = "Hold"
    decision_title = "Stock Healthy"
    confidence_score = 0.85
    explanation_summary = ""
    primary_factors = []
    risk_factors = []
    alternative_actions = []
    
    if include_explanation and 'xai' in modules:
        try:
            exp_result = modules['xai']['generate_explanation'](
                sku=sku,
                product_name=product_name,
                current_stock=current_stock,
                forecasted_demand=forecasted_demand,
                safety_stock=safety_stock,
                reorder_point=reorder_point,
                lead_time_days=lead_time,
                unit_cost=unit_cost
            )
            if exp_result.get('success'):
                decision = exp_result.get('decision', decision)
                decision_title = exp_result.get('decision_title', decision_title)
                confidence_score = exp_result.get('confidence', confidence_score)
                explanation_summary = exp_result.get('summary', '')
                primary_factors = exp_result.get('primary_factors', [])
                risk_factors = exp_result.get('risk_factors', [])
                alternative_actions = exp_result.get('alternative_actions', [])
                result['detailed_explanation'] = exp_result.get('detailed_explanation', '')
        except Exception as e:
            logger.warning(f"XAI explanation failed: {e}")
    
    result.update({
        'decision': decision,
        'decision_title': decision_title,
        'confidence_score': confidence_score,
        'explanation_summary': explanation_summary,
        'primary_factors': primary_factors,
        'risk_factors': risk_factors,
        'alternative_actions': alternative_actions
    })
    
    # Generate email if restock needed
    if units_to_order > 0 and 'reports' in modules:
        try:
            generator = modules['reports']['IntelligentReportGenerator']()
            email = await generator.generate_supplier_email(
                email_type='order',
                context={
                    'supplier_name': supplier_name,
                    'product_name': product_name,
                    'quantity': units_to_order,
                    'urgency': order_urgency
                }
            )
            result['email_draft'] = {
                'subject': email.subject,
                'body': email.body,
                'ai_generated': email.ai_generated
            }
        except Exception as e:
            logger.warning(f"Email generation failed: {e}")
    
    result['success'] = True
    return result


@router.post("/analyze-all", response_model=BatchAnalysisResponse, tags=["Enhanced Analysis"])
async def enhanced_batch_analysis():
    """
    Run enhanced analysis for all SKUs in inventory.
    Returns summary with prioritized recommendations.
    """
    try:
        from src.api import load_supply_chain_data
        
        df = load_supply_chain_data()
        skus = df['SKU'].unique().tolist()
        
        results = []
        restock_urgent = 0
        restock_soon = 0
        healthy = 0
        overstock = 0
        total_order_value = 0
        
        for sku in skus:
            try:
                analysis = await enhanced_sku_analysis(
                    sku=sku,
                    include_forecast=True,
                    include_optimization=True,
                    include_supplier=False,  # Skip for batch to save time
                    include_explanation=True
                )
                
                # Categorize
                decision = analysis.get('decision', 'hold')
                if decision == 'restock_urgent':
                    restock_urgent += 1
                elif decision == 'restock_soon':
                    restock_soon += 1
                elif decision == 'reduce_stock':
                    overstock += 1
                else:
                    healthy += 1
                
                order_value = analysis.get('units_to_order', 0) * analysis.get('current_stock', 0) / 100  # Approximate
                total_order_value += order_value
                
                results.append({
                    'sku': sku,
                    'product_name': analysis.get('product_name', ''),
                    'decision': decision,
                    'stock_status': analysis.get('stock_status', ''),
                    'units_to_order': analysis.get('units_to_order', 0),
                    'order_urgency': analysis.get('order_urgency', 'not_needed'),
                    'confidence': analysis.get('confidence_score', 0)
                })
                
            except Exception as e:
                logger.warning(f"Analysis failed for {sku}: {e}")
                results.append({
                    'sku': sku,
                    'error': str(e)
                })
        
        # Sort by urgency
        results.sort(key=lambda x: (
            0 if x.get('order_urgency') == 'immediate' else
            1 if x.get('order_urgency') == 'high' else
            2 if x.get('order_urgency') == 'medium' else 3
        ))
        
        return BatchAnalysisResponse(
            total_analyzed=len(results),
            restock_urgent=restock_urgent,
            restock_soon=restock_soon,
            healthy=healthy,
            overstock=overstock,
            total_order_value=round(total_order_value, 2),
            results=results
        )
        
    except Exception as e:
        logger.error(f"Batch analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/report", tags=["Reports"])
async def generate_report_endpoint(request: ReportRequest):
    """
    Generate AI-powered reports.
    
    Report types:
    - executive_summary: Weekly/monthly executive summary
    - procurement: Procurement recommendation for specific SKU
    - email: Generate supplier communication
    """
    modules = get_modules()
    
    if 'reports' not in modules:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report generator module not available"
        )
    
    try:
        from src.api import load_supply_chain_data
        
        df = load_supply_chain_data()
        
        # Convert to list
        inventory_data = []
        for sku in df['SKU'].unique():
            sku_data = df[df['SKU'] == sku].iloc[0]
            inventory_data.append({
                'sku': str(sku_data['SKU']),
                'product_name': str(sku_data['Product_Name']),
                'category': str(sku_data['Category']),
                'current_stock': int(sku_data['Current_Stock']),
                'cost_per_unit': float(sku_data['Cost_Per_Unit']),
                'supplier': str(sku_data['Supplier']),
                'defect_rate': float(sku_data['Defect_Rate']),
                'lead_time_days': int(sku_data['Lead_Time_Days'])
            })
        
        generator = modules['reports']['IntelligentReportGenerator']()
        
        if request.report_type == 'executive_summary':
            report = await generator.generate_executive_summary(
                inventory_data,
                period=request.period
            )
            from dataclasses import asdict
            return {'success': True, **asdict(report)}
        
        elif request.report_type == 'procurement' and request.sku:
            # Find product
            product = next((p for p in inventory_data if p['sku'].upper() == request.sku.upper()), None)
            if not product:
                raise HTTPException(status_code=404, detail=f"SKU {request.sku} not found")
            
            report = await generator.generate_procurement_recommendation(
                sku=request.sku,
                product_data=product,
                forecast={'forecasted_demand_30_days': product['current_stock'] * 0.5}
            )
            from dataclasses import asdict
            return {'success': True, **asdict(report)}
        
        elif request.report_type == 'email':
            report = await generator.generate_supplier_email(
                email_type=request.email_type or 'inquiry',
                context=request.email_context or {}
            )
            from dataclasses import asdict
            return {'success': True, **asdict(report)}
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid report type: {request.report_type}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/supplier/score", tags=["Supplier Analysis"])
async def score_supplier_endpoint(request: SupplierScoreRequest):
    """
    Generate comprehensive supplier scorecard.
    """
    modules = get_modules()
    
    if 'supplier' not in modules:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supplier scoring module not available"
        )
    
    try:
        result = modules['supplier']['score_supplier'](
            supplier_name=request.supplier_name,
            defect_rate=request.defect_rate,
            lead_time_days=request.lead_time_days,
            on_time_rate=request.on_time_rate,
            unit_cost=request.unit_cost,
            market_avg_cost=request.market_avg_cost
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Supplier scoring failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# SAMPLE QUERIES ENDPOINT (FOR DEMO/TESTING)
# =============================================================================

@router.get("/sample-queries", tags=["Natural Language"])
async def get_sample_queries():
    """Get sample natural language queries for demo purposes."""
    return {
        "sample_queries": [
            {
                "query": "Which products will face stockout next week?",
                "intent": "stockout_risk",
                "description": "Find products at risk of running out"
            },
            {
                "query": "Show me slow-moving items",
                "intent": "overstock",
                "description": "Identify dead or slow-moving stock"
            },
            {
                "query": "What should I order this week?",
                "intent": "reorder",
                "description": "Get reorder recommendations"
            },
            {
                "query": "Give me an executive summary",
                "intent": "summary",
                "description": "Overall inventory health summary"
            },
            {
                "query": "Tell me about SKU-001",
                "intent": "specific_product",
                "description": "Get details about a specific product"
            },
            {
                "query": "What's the total inventory value?",
                "intent": "cost",
                "description": "Financial analysis of inventory"
            }
        ],
        "usage": "POST /api/v2/query with {\"query\": \"your question here\"}"
    }
