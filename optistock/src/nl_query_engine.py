# src/nl_query_engine.py
"""
OptiStock: Natural Language Query Engine
Translates business questions into data queries and generates insights.
Powered by Gemini AI with fallback to rule-based responses.
"""

import os
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import Gemini
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-generativeai not installed - using rule-based responses only")


class NaturalLanguageQueryEngine:
    """
    Natural language interface for inventory queries.
    Translates business questions into data queries and generates insights.
    
    Features:
    - Intent classification for query routing
    - Context-aware responses using inventory data
    - Gemini AI integration for natural responses
    - Rule-based fallback for offline operation
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        self.model = None
        
        if self.api_key and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                logger.info("✅ NL Query Engine initialized with Gemini AI")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
        else:
            logger.info("NL Query Engine running in rule-based mode")
        
        # Query intent patterns
        self.intent_patterns = {
            'stockout_risk': [
                r'stockout', r'run\s*out', r'shortage', r'at\s*risk', r'low\s*stock',
                r'running\s*low', r'depleting', r'need\s*to\s*order'
            ],
            'demand_forecast': [
                r'forecast', r'predict', r'demand', r'sales\s*forecast',
                r'next\s*week', r'next\s*month', r'expected\s*sales', r'projection'
            ],
            'supplier': [
                r'supplier', r'vendor', r'lead\s*time', r'delivery',
                r'reliability', r'supplier\s*issue', r'late\s*delivery'
            ],
            'overstock': [
                r'overstock', r'excess', r'dead\s*stock', r'slow\s*moving',
                r'too\s*much', r'overstocked', r'not\s*selling'
            ],
            'reorder': [
                r'reorder', r'order\s*now', r'purchase', r'buy',
                r'replenish', r'what\s*to\s*order', r'procurement'
            ],
            'cost': [
                r'cost', r'price', r'value', r'expensive', r'profit',
                r'margin', r'revenue', r'spending', r'budget'
            ],
            'summary': [
                r'summary', r'overview', r'status', r'report',
                r'how\s*are\s*we', r'dashboard', r'health', r'overall'
            ],
            'specific_product': [
                r'sku[\s-]*\w+', r'product\s+\w+', r'about\s+\w+',
                r'tell\s*me\s*about', r'status\s*of'
            ]
        }
    
    def classify_intent(self, query: str) -> str:
        """Classify query intent based on patterns."""
        query_lower = query.lower()
        
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent
        
        return 'general'
    
    def extract_sku_from_query(self, query: str) -> Optional[str]:
        """Extract SKU reference from query if present."""
        # Pattern for SKU-XXX format
        sku_match = re.search(r'sku[\s-]*(\w+)', query.lower())
        if sku_match:
            return f"SKU-{sku_match.group(1).upper()}"
        
        # Pattern for just the code
        code_match = re.search(r'\b([A-Z]{2,3}[-]?\d{3,4})\b', query.upper())
        if code_match:
            return code_match.group(1)
        
        return None
    
    def build_context(self, 
                     inventory_data: List[Dict], 
                     analytics: Dict = None) -> str:
        """Build context string for LLM."""
        
        analytics = analytics or {}
        
        # Calculate summary stats
        total_skus = len(inventory_data)
        total_value = sum(
            (item.get('current_stock', 0) or 0) * (item.get('cost_per_unit', 0) or 0) 
            for item in inventory_data
        )
        
        # Identify risk items
        stockout_risk = [
            item for item in inventory_data 
            if (item.get('current_stock', 0) or 0) <= 50
        ]
        
        overstock = [
            item for item in inventory_data
            if (item.get('current_stock', 0) or 0) > 500
        ]
        
        context = f"""
You are OptiStock AI, an intelligent inventory management assistant for MSMEs (Micro, Small, and Medium Enterprises).
You help business owners make smart inventory decisions using AI-powered insights.

Current Date: {datetime.now().strftime('%B %d, %Y')}

=== INVENTORY SUMMARY ===
• Total Products: {total_skus}
• Total Stock Value: ₹{total_value:,.0f}
• Products at Stockout Risk (≤50 units): {len(stockout_risk)}
• Products Potentially Overstocked (>500 units): {len(overstock)}

=== PRODUCTS AT RISK ===
{json.dumps([{'sku': p['sku'], 'name': p.get('product_name', 'Unknown'), 'stock': p.get('current_stock', 0)} for p in stockout_risk[:5]], indent=2) if stockout_risk else 'No products at immediate risk'}

=== TOP PRODUCTS BY VALUE ===
{json.dumps([{'sku': p['sku'], 'name': p.get('product_name', 'Unknown'), 'stock': p.get('current_stock', 0), 'value': round(p.get('current_stock', 0) * p.get('cost_per_unit', 0), 2)} for p in sorted(inventory_data, key=lambda x: (x.get('current_stock', 0) or 0) * (x.get('cost_per_unit', 0) or 0), reverse=True)[:5]], indent=2)}

=== RESPONSE GUIDELINES ===
1. Be concise but informative
2. Always cite specific product names and SKUs
3. Prioritize by business impact
4. Suggest specific, actionable steps
5. Use ₹ for currency
6. Format numbers with Indian number system (lakhs, crores) for large values
        """
        
        return context
    
    async def process_query(self, 
                           query: str, 
                           inventory_data: List[Dict],
                           analytics: Dict = None) -> Dict:
        """
        Process natural language query and generate response.
        
        Args:
            query: User's question in natural language
            inventory_data: List of inventory items
            analytics: Additional analytics data (optional)
            
        Returns:
            Dict with response and metadata
        """
        intent = self.classify_intent(query)
        extracted_sku = self.extract_sku_from_query(query)
        
        # Try AI response first
        if self.model:
            try:
                context = self.build_context(inventory_data, analytics)
                
                prompt = f"""
{context}

=== USER QUESTION ===
{query}

=== INSTRUCTIONS ===
Provide a helpful, specific response addressing the user's question.
- Include relevant product names (SKUs) and specific numbers
- Format important figures (use ₹ for currency)
- Use bullet points for lists
- Keep response under 300 words
- End with a clear action recommendation if applicable
                """
                
                response = self.model.generate_content(prompt)
                
                # Extract mentioned products
                products_mentioned = self._extract_products(response.text, inventory_data)
                
                # Extract actions
                actions = self._extract_actions(response.text)
                
                return {
                    'success': True,
                    'query': query,
                    'intent': intent,
                    'response': response.text,
                    'products_mentioned': products_mentioned,
                    'suggested_actions': actions,
                    'extracted_sku': extracted_sku,
                    'ai_powered': True
                }
            
            except Exception as e:
                logger.warning(f"Gemini query failed: {e}, falling back to rules")
        
        # Fallback to rule-based response
        fallback_response = self._generate_rule_based_response(
            query, intent, inventory_data, extracted_sku
        )
        
        return {
            'success': True,
            'query': query,
            'intent': intent,
            'response': fallback_response,
            'products_mentioned': [],
            'suggested_actions': [],
            'extracted_sku': extracted_sku,
            'ai_powered': False
        }
    
    def _generate_rule_based_response(self,
                                      query: str,
                                      intent: str,
                                      inventory_data: List[Dict],
                                      extracted_sku: str = None) -> str:
        """Generate rule-based response when AI is unavailable."""
        
        if intent == 'stockout_risk':
            at_risk = [
                p for p in inventory_data 
                if (p.get('current_stock', 0) or 0) <= 50
            ]
            if at_risk:
                products = ", ".join([f"{p['sku']} ({p.get('current_stock', 0)} units)" for p in at_risk[:5]])
                return f"📊 **Stockout Risk Alert**\n\nFound {len(at_risk)} products at risk:\n{products}\n\n**Action:** Review these items and consider placing orders for the most critical ones."
            return "✅ No products are currently at stockout risk. All stock levels appear healthy."
        
        elif intent == 'summary':
            total = len(inventory_data)
            value = sum(
                (p.get('current_stock', 0) or 0) * (p.get('cost_per_unit', 0) or 0) 
                for p in inventory_data
            )
            low_stock = len([p for p in inventory_data if (p.get('current_stock', 0) or 0) <= 50])
            
            return f"""📈 **Inventory Summary**

• **Total Products:** {total}
• **Total Stock Value:** ₹{value:,.0f}
• **Low Stock Alerts:** {low_stock}

**Status:** {'⚠️ Attention needed for ' + str(low_stock) + ' products' if low_stock > 0 else '✅ Inventory levels healthy'}"""
        
        elif intent == 'overstock':
            overstock = [
                p for p in inventory_data 
                if (p.get('current_stock', 0) or 0) > 500
            ]
            if overstock:
                products = ", ".join([f"{p['sku']} ({p.get('current_stock', 0)} units)" for p in overstock[:5]])
                return f"📦 **Overstock Alert**\n\nFound {len(overstock)} potentially overstocked items:\n{products}\n\n**Action:** Consider promotions or transfers to reduce excess inventory."
            return "✅ No significant overstock detected in your inventory."
        
        elif intent == 'reorder':
            to_reorder = [
                p for p in inventory_data 
                if (p.get('current_stock', 0) or 0) <= 100
            ]
            if to_reorder:
                products = "\n".join([f"• {p['sku']} - {p.get('product_name', 'Unknown')} ({p.get('current_stock', 0)} units left)" for p in to_reorder[:10]])
                return f"🛒 **Reorder Recommendations**\n\nThese products need restocking:\n{products}\n\n**Action:** Prioritize items with lowest stock levels."
            return "✅ No immediate reorders needed. Stock levels are healthy."
        
        elif intent == 'specific_product' and extracted_sku:
            product = next((p for p in inventory_data if p['sku'].upper() == extracted_sku.upper()), None)
            if product:
                return f"""📋 **Product Details: {extracted_sku}**

• **Name:** {product.get('product_name', 'N/A')}
• **Category:** {product.get('category', 'N/A')}
• **Current Stock:** {product.get('current_stock', 0)} units
• **Cost/Unit:** ₹{product.get('cost_per_unit', 0):.2f}
• **Supplier:** {product.get('supplier', 'N/A')}
• **Lead Time:** {product.get('lead_time_days', 'N/A')} days

**Stock Value:** ₹{(product.get('current_stock', 0) or 0) * (product.get('cost_per_unit', 0) or 0):,.2f}"""
            return f"❓ Product {extracted_sku} not found in inventory."
        
        elif intent == 'cost':
            total_value = sum(
                (p.get('current_stock', 0) or 0) * (p.get('cost_per_unit', 0) or 0) 
                for p in inventory_data
            )
            top_value = sorted(
                inventory_data, 
                key=lambda x: (x.get('current_stock', 0) or 0) * (x.get('cost_per_unit', 0) or 0),
                reverse=True
            )[:5]
            
            products = "\n".join([
                f"• {p['sku']}: ₹{(p.get('current_stock', 0) or 0) * (p.get('cost_per_unit', 0) or 0):,.0f}" 
                for p in top_value
            ])
            
            return f"""💰 **Inventory Value Analysis**

**Total Inventory Value:** ₹{total_value:,.0f}

**Top 5 by Value:**
{products}

**Tip:** Focus on optimizing stock levels for high-value items to improve cash flow."""
        
        # General fallback
        return f"""🤖 I understand you're asking about: "{query}"

Here's what I can help you with:
• **"What products are at stockout risk?"** - Find low stock items
• **"Give me an inventory summary"** - Overview of stock status
• **"What should I reorder?"** - Get reorder recommendations
• **"Tell me about SKU-XXX"** - Get specific product details
• **"What's overstocked?"** - Find excess inventory

Try asking one of these questions for detailed insights!"""
    
    def _extract_products(self, text: str, inventory_data: List[Dict]) -> List[str]:
        """Extract mentioned product SKUs from response."""
        mentioned = []
        text_upper = text.upper()
        
        for product in inventory_data:
            sku = product['sku'].upper()
            if sku in text_upper:
                mentioned.append(product['sku'])
            elif product.get('product_name', '').upper() in text_upper:
                mentioned.append(product['sku'])
        
        return list(set(mentioned))[:5]
    
    def _extract_actions(self, text: str) -> List[str]:
        """Extract actionable recommendations from response."""
        action_keywords = ['order', 'restock', 'reduce', 'negotiate', 'monitor', 'check', 'review', 'consider']
        actions = []
        
        for line in text.split('\n'):
            line = line.strip()
            if any(kw in line.lower() for kw in action_keywords):
                # Clean up the line
                clean_line = re.sub(r'^[\-\•\*]\s*', '', line)
                if len(clean_line) > 10 and len(clean_line) < 200:
                    actions.append(clean_line)
        
        return list(set(actions))[:5]


# Sample queries for documentation/testing
SAMPLE_QUERIES = [
    "Which products will face stockout next week?",
    "Show me slow-moving items",
    "What should I order this week?",
    "Give me an executive summary",
    "Tell me about SKU-001",
    "What's the total inventory value?",
    "Which suppliers are causing delays?",
    "What products are overstocked?",
]


async def query_inventory(query: str, inventory_data: List[Dict]) -> Dict:
    """
    Convenience function for natural language queries.
    
    Args:
        query: Natural language question
        inventory_data: List of inventory items
        
    Returns:
        Dict with response
    """
    engine = NaturalLanguageQueryEngine()
    return await engine.process_query(query, inventory_data)
