# src/report_generator.py
"""
OptiStock: AI-Powered Report Generator
Generates executive summaries, procurement recommendations, and supplier emails.
"""

import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

# Try to import Gemini
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


@dataclass
class ExecutiveSummary:
    """Executive summary report structure."""
    title: str
    period: str
    generated_at: str
    
    # Key metrics
    total_skus: int
    total_value: float
    stockout_risk_count: int
    overstock_count: int
    
    # Health score
    inventory_health_score: int  # 0-100
    health_grade: str  # A, B, C, D, F
    
    # Highlights
    key_wins: List[str]
    key_concerns: List[str]
    
    # Recommendations
    immediate_actions: List[str]
    strategic_recommendations: List[str]
    
    # AI-generated narrative
    narrative: str
    
    ai_generated: bool


@dataclass 
class ProcurementRecommendation:
    """Procurement recommendation structure."""
    sku: str
    product_name: str
    
    # Order details
    recommended_quantity: int
    estimated_cost: float
    order_urgency: str
    
    # Supplier info
    supplier_name: str
    expected_lead_time: int
    
    # Reasoning
    recommendation_text: str
    negotiation_tips: List[str]
    risk_considerations: List[str]
    
    ai_generated: bool


@dataclass
class SupplierEmail:
    """Generated supplier email."""
    email_type: str  # order, negotiation, complaint, inquiry
    subject: str
    body: str
    supplier_name: str
    
    # Metadata
    generated_at: str
    ai_generated: bool


class IntelligentReportGenerator:
    """
    Generates executive summaries, procurement recommendations, and emails.
    Uses Gemini AI with fallback to templates.
    
    Features:
    - Weekly/monthly executive summaries
    - Per-product procurement recommendations
    - AI-generated supplier communication
    - Negotiation strategy suggestions
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        self.model = None
        
        if self.api_key and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                logger.info("✅ Report Generator initialized with Gemini AI")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
    
    def calculate_health_score(self, 
                              inventory_data: List[Dict],
                              analytics: Dict = None) -> tuple:
        """Calculate overall inventory health score."""
        
        if not inventory_data:
            return 50, 'C'
        
        total_items = len(inventory_data)
        
        # Count issues
        stockout_risk = len([
            p for p in inventory_data 
            if (p.get('current_stock', 0) or 0) <= 20
        ])
        
        low_stock = len([
            p for p in inventory_data 
            if 20 < (p.get('current_stock', 0) or 0) <= 50
        ])
        
        overstock = len([
            p for p in inventory_data 
            if (p.get('current_stock', 0) or 0) > 500
        ])
        
        # Calculate score (start at 100, deduct for issues)
        score = 100
        score -= (stockout_risk / total_items) * 40  # Critical issues
        score -= (low_stock / total_items) * 20  # Moderate issues
        score -= (overstock / total_items) * 15  # Overstock penalty
        
        score = max(0, min(100, score))
        
        # Determine grade
        if score >= 90:
            grade = 'A'
        elif score >= 75:
            grade = 'B'
        elif score >= 60:
            grade = 'C'
        elif score >= 45:
            grade = 'D'
        else:
            grade = 'F'
        
        return int(score), grade
    
    async def generate_executive_summary(self,
                                        inventory_data: List[Dict],
                                        analytics: Dict = None,
                                        period: str = 'weekly') -> ExecutiveSummary:
        """
        Generate executive summary report.
        
        Args:
            inventory_data: List of inventory items
            analytics: Additional analytics (forecasts, etc.)
            period: 'weekly' or 'monthly'
        """
        analytics = analytics or {}
        
        # Calculate metrics
        total_skus = len(inventory_data)
        total_value = sum(
            (p.get('current_stock', 0) or 0) * (p.get('cost_per_unit', 0) or 0)
            for p in inventory_data
        )
        
        stockout_risk = [
            p for p in inventory_data
            if (p.get('current_stock', 0) or 0) <= 50
        ]
        
        overstock = [
            p for p in inventory_data
            if (p.get('current_stock', 0) or 0) > 500
        ]
        
        health_score, health_grade = self.calculate_health_score(inventory_data, analytics)
        
        # Generate key wins and concerns
        key_wins = []
        key_concerns = []
        
        if len(stockout_risk) == 0:
            key_wins.append("No products at critical stockout risk")
        else:
            key_concerns.append(f"{len(stockout_risk)} products at stockout risk requiring immediate attention")
        
        if health_score >= 80:
            key_wins.append(f"Overall inventory health score: {health_score}/100 (Excellent)")
        elif health_score < 60:
            key_concerns.append(f"Inventory health score below target: {health_score}/100")
        
        if len(overstock) > 0:
            overstock_value = sum(
                (p.get('current_stock', 0) or 0) * (p.get('cost_per_unit', 0) or 0)
                for p in overstock
            )
            key_concerns.append(f"₹{overstock_value:,.0f} tied up in {len(overstock)} overstocked items")
        
        # Generate recommendations
        immediate_actions = []
        strategic_recommendations = []
        
        if stockout_risk:
            skus = ", ".join([p['sku'] for p in stockout_risk[:3]])
            immediate_actions.append(f"Urgent: Place orders for {skus}")
        
        if overstock:
            immediate_actions.append("Review overstock items for promotional pricing opportunities")
        
        strategic_recommendations.append("Implement automated reorder alerts for all SKUs")
        strategic_recommendations.append("Review supplier lead times and negotiate faster delivery")
        
        # Try AI-generated narrative
        narrative = ""
        ai_generated = False
        
        if self.model:
            try:
                prompt = f"""
Generate a 2-paragraph executive summary for an MSME inventory report.

Key Data:
- Period: {period.title()}
- Total SKUs: {total_skus}
- Total Inventory Value: ₹{total_value:,.0f}
- Stockout Risk Items: {len(stockout_risk)}
- Overstock Items: {len(overstock)}
- Health Score: {health_score}/100 ({health_grade})

Key Wins: {', '.join(key_wins) if key_wins else 'None noted'}
Key Concerns: {', '.join(key_concerns) if key_concerns else 'None noted'}

Write in professional business language. Be concise. Focus on actionable insights.
                """
                
                response = self.model.generate_content(prompt)
                narrative = response.text
                ai_generated = True
                
            except Exception as e:
                logger.warning(f"AI narrative generation failed: {e}")
        
        if not narrative:
            narrative = self._template_narrative(
                period, total_skus, total_value, len(stockout_risk),
                len(overstock), health_score, health_grade
            )
        
        return ExecutiveSummary(
            title=f"OptiStock {period.title()} Executive Summary",
            period=period,
            generated_at=datetime.now().isoformat(),
            total_skus=total_skus,
            total_value=round(total_value, 2),
            stockout_risk_count=len(stockout_risk),
            overstock_count=len(overstock),
            inventory_health_score=health_score,
            health_grade=health_grade,
            key_wins=key_wins,
            key_concerns=key_concerns,
            immediate_actions=immediate_actions,
            strategic_recommendations=strategic_recommendations,
            narrative=narrative,
            ai_generated=ai_generated
        )
    
    async def generate_procurement_recommendation(self,
                                                  sku: str,
                                                  product_data: Dict,
                                                  forecast: Dict,
                                                  supplier_data: Dict = None) -> ProcurementRecommendation:
        """
        Generate specific procurement recommendation.
        """
        supplier_data = supplier_data or {}
        
        current_stock = product_data.get('current_stock', 0)
        forecasted_demand = forecast.get('forecasted_demand', 0) or forecast.get('forecasted_demand_30_days', 0)
        unit_cost = product_data.get('cost_per_unit', 0)
        lead_time = product_data.get('lead_time_days', 7)
        supplier_name = product_data.get('supplier', 'Unknown Supplier')
        
        # Calculate recommended quantity
        safety_buffer = int(forecasted_demand * 0.2)
        units_needed = max(0, forecasted_demand + safety_buffer - current_stock)
        estimated_cost = units_needed * unit_cost
        
        # Determine urgency
        days_of_supply = current_stock / (forecasted_demand / 30) if forecasted_demand > 0 else 999
        if days_of_supply < 7:
            urgency = "immediate"
        elif days_of_supply < 14:
            urgency = "high"
        elif days_of_supply < 30:
            urgency = "medium"
        else:
            urgency = "low"
        
        # Generate negotiation tips and risks
        negotiation_tips = []
        risk_considerations = []
        
        if units_needed > 100:
            negotiation_tips.append("Request 5-10% bulk discount for order size")
        
        if urgency == "immediate":
            negotiation_tips.append("Ask about expedited shipping options")
            risk_considerations.append("Rush order may incur premium pricing")
        
        negotiation_tips.append("Confirm lead time commitment in writing")
        risk_considerations.append(f"Standard lead time: {lead_time} days")
        
        # Try AI-generated recommendation
        recommendation_text = ""
        ai_generated = False
        
        if self.model and units_needed > 0:
            try:
                prompt = f"""
Generate a brief procurement recommendation (3-4 sentences) for an MSME:

Product: {product_data.get('product_name', sku)} ({sku})
Current Stock: {current_stock} units
30-Day Forecast: {forecasted_demand} units
Units to Order: {units_needed} units
Estimated Cost: ₹{estimated_cost:,.0f}
Supplier: {supplier_name}
Urgency: {urgency}

Include specific quantity, timing, and one negotiation tip.
                """
                
                response = self.model.generate_content(prompt)
                recommendation_text = response.text
                ai_generated = True
                
            except Exception as e:
                logger.warning(f"AI recommendation failed: {e}")
        
        if not recommendation_text:
            if units_needed > 0:
                recommendation_text = f"Order {units_needed} units of {product_data.get('product_name', sku)} from {supplier_name}. Estimated cost: ₹{estimated_cost:,.0f}. Priority: {urgency.upper()}. Expected delivery: {lead_time} days after order."
            else:
                recommendation_text = f"No immediate order needed for {product_data.get('product_name', sku)}. Current stock ({current_stock} units) is sufficient to meet forecasted demand."
        
        return ProcurementRecommendation(
            sku=sku,
            product_name=product_data.get('product_name', 'Unknown'),
            recommended_quantity=units_needed,
            estimated_cost=round(estimated_cost, 2),
            order_urgency=urgency,
            supplier_name=supplier_name,
            expected_lead_time=lead_time,
            recommendation_text=recommendation_text,
            negotiation_tips=negotiation_tips,
            risk_considerations=risk_considerations,
            ai_generated=ai_generated
        )
    
    async def generate_supplier_email(self,
                                      email_type: str,
                                      context: Dict) -> SupplierEmail:
        """
        Generate professional supplier email.
        
        Args:
            email_type: 'order', 'negotiation', 'complaint', 'inquiry'
            context: Dict with supplier_name, product_name, quantity, etc.
        """
        supplier_name = context.get('supplier_name', 'Supplier')
        product_name = context.get('product_name', 'products')
        quantity = context.get('quantity', 0)
        urgency = context.get('urgency', 'normal')
        notes = context.get('notes', '')
        
        subject = ""
        body = ""
        ai_generated = False
        
        # Try AI generation
        if self.model:
            try:
                type_descriptions = {
                    'order': "placing a purchase order",
                    'negotiation': "negotiating better pricing/terms",
                    'complaint': "addressing a delivery or quality issue",
                    'inquiry': "requesting quote and availability"
                }
                
                prompt = f"""
Draft a professional but friendly email for {type_descriptions.get(email_type, 'business inquiry')}.

Context:
- Supplier: {supplier_name}
- Product: {product_name}
- Quantity: {quantity} units
- Urgency: {urgency}
- Additional Notes: {notes or 'None'}

Requirements:
1. Professional but warm tone (suitable for MSME relationship)
2. Clear and specific about requirements
3. Include call-to-action
4. Keep under 150 words

Format response as:
Subject: [subject line]

[email body]
                """
                
                response = self.model.generate_content(prompt)
                text = response.text
                
                # Parse subject and body
                if 'Subject:' in text:
                    parts = text.split('\n', 2)
                    subject = parts[0].replace('Subject:', '').strip()
                    body = '\n'.join(parts[1:]).strip()
                else:
                    subject = f"{email_type.title()} Inquiry - {product_name}"
                    body = text
                
                ai_generated = True
                
            except Exception as e:
                logger.warning(f"AI email generation failed: {e}")
        
        # Fallback to templates
        if not subject or not body:
            subject, body = self._template_email(email_type, context)
        
        return SupplierEmail(
            email_type=email_type,
            subject=subject,
            body=body,
            supplier_name=supplier_name,
            generated_at=datetime.now().isoformat(),
            ai_generated=ai_generated
        )
    
    def _template_narrative(self, period, total_skus, total_value, 
                           stockout_count, overstock_count, score, grade) -> str:
        """Generate template-based narrative."""
        
        health_status = "excellent" if score >= 85 else "good" if score >= 70 else "needs attention" if score >= 55 else "concerning"
        
        return f"""
Your inventory health for this {period} period is **{health_status}** with a score of {score}/100 (Grade: {grade}).

You are managing {total_skus} products with a total inventory value of ₹{total_value:,.0f}. {"There are " + str(stockout_count) + " items requiring immediate attention due to low stock levels." if stockout_count > 0 else "All stock levels are within healthy ranges."} {"Additionally, " + str(overstock_count) + " items appear overstocked and may be tying up working capital." if overstock_count > 0 else ""}

**Key Focus Areas:** {"Address stockout risks immediately to avoid lost sales." if stockout_count > 0 else "Maintain current inventory practices."} {"Consider promotional activities for overstocked items." if overstock_count > 0 else ""}
        """.strip()
    
    def _template_email(self, email_type: str, context: Dict) -> tuple:
        """Generate template-based email."""
        
        supplier = context.get('supplier_name', 'Supplier')
        product = context.get('product_name', 'products')
        quantity = context.get('quantity', 0)
        
        templates = {
            'order': (
                f"Purchase Order Inquiry - {product}",
                f"""Dear {supplier} Team,

We would like to place an order for {quantity} units of {product}.

Please confirm:
1. Current availability
2. Unit pricing for this quantity
3. Expected delivery timeline

Looking forward to your prompt response.

Best regards,
OptiStock Procurement Team"""
            ),
            'negotiation': (
                f"Pricing Discussion - {product}",
                f"""Dear {supplier} Team,

We have been pleased with our partnership and are looking to increase our order volume for {product}.

Given our growing demand, we would like to discuss:
1. Volume-based pricing for orders of {quantity}+ units
2. Potential for extended payment terms
3. Expedited delivery options

Would you be available for a call this week to discuss?

Best regards,
OptiStock Procurement Team"""
            ),
            'inquiry': (
                f"Product Inquiry - {product}",
                f"""Dear {supplier} Team,

We are interested in sourcing {product} for our inventory.

Could you please provide:
1. Product specifications and availability
2. Pricing for quantities of {quantity} units
3. Lead time for delivery
4. Minimum order quantities

Thank you for your assistance.

Best regards,
OptiStock Procurement Team"""
            ),
            'complaint': (
                f"Urgent: Order Issue - {product}",
                f"""Dear {supplier} Team,

We need to bring to your attention an issue with our recent order of {product}.

{context.get('notes', 'Please contact us to discuss the matter.')}

We request immediate attention to this matter and a resolution plan.

Please contact us at your earliest convenience.

Best regards,
OptiStock Procurement Team"""
            )
        }
        
        return templates.get(email_type, templates['inquiry'])


async def generate_report(
    inventory_data: List[Dict],
    report_type: str = 'executive_summary',
    **kwargs
) -> Dict:
    """
    Convenience function for report generation.
    
    Args:
        inventory_data: List of inventory items
        report_type: 'executive_summary', 'procurement', 'email'
        **kwargs: Additional parameters for specific report types
        
    Returns:
        Dict with generated report
    """
    generator = IntelligentReportGenerator()
    
    try:
        if report_type == 'executive_summary':
            result = await generator.generate_executive_summary(
                inventory_data,
                analytics=kwargs.get('analytics'),
                period=kwargs.get('period', 'weekly')
            )
        elif report_type == 'procurement':
            result = await generator.generate_procurement_recommendation(
                sku=kwargs.get('sku', 'UNKNOWN'),
                product_data=kwargs.get('product_data', {}),
                forecast=kwargs.get('forecast', {}),
                supplier_data=kwargs.get('supplier_data')
            )
        elif report_type == 'email':
            result = await generator.generate_supplier_email(
                email_type=kwargs.get('email_type', 'inquiry'),
                context=kwargs.get('context', {})
            )
        else:
            return {'success': False, 'error': f'Unknown report type: {report_type}'}
        
        return {
            'success': True,
            **asdict(result)
        }
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
