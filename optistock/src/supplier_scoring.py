# src/supplier_scoring.py
"""
OptiStock: Supplier Reliability Scoring System
Multi-dimensional supplier evaluation with explainable metrics.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class SupplierScore:
    """Individual score component."""
    score: float
    max_score: float
    weight: float
    details: Dict
    interpretation: str


@dataclass
class SupplierScorecard:
    """Complete supplier evaluation."""
    supplier_name: str
    supplier_id: str
    
    # Overall metrics
    reliability_score: float  # 0-100
    overall_grade: str  # A, B, C, D, F
    risk_level: str  # Low, Medium, High, Critical
    
    # Component scores
    delivery_score: float
    quality_score: float
    price_score: float
    responsiveness_score: float
    
    # Details
    delivery_details: Dict
    quality_details: Dict
    price_details: Dict
    responsiveness_details: Dict
    
    # Recommendations
    recommendations: List[str]
    risk_factors: List[str]
    strengths: List[str]
    
    # Trend
    trend: str  # "improving", "stable", "declining"
    last_updated: str


class SupplierReliabilityScorer:
    """
    Multi-dimensional supplier scoring with explainable metrics.
    
    Scoring Dimensions:
    - Delivery (35%): On-time delivery, lead time consistency
    - Quality (30%): Defect rate, return rate, quality incidents
    - Price (20%): Competitiveness, stability, discount availability
    - Responsiveness (15%): Communication, issue resolution time
    """
    
    def __init__(self):
        # Weights for overall score
        self.weights = {
            'delivery': 0.35,
            'quality': 0.30,
            'price': 0.20,
            'responsiveness': 0.15
        }
        
        # Grade thresholds
        self.grade_thresholds = {
            'A': 90,
            'B': 75,
            'C': 60,
            'D': 45,
            'F': 0
        }
        
        # Risk level thresholds
        self.risk_thresholds = {
            'Low': 75,
            'Medium': 60,
            'High': 45,
            'Critical': 0
        }
    
    def calculate_delivery_score(self,
                                on_time_deliveries: int,
                                total_deliveries: int,
                                avg_delay_days: float = 0,
                                lead_time_variance: float = 0) -> SupplierScore:
        """
        Score supplier on delivery performance.
        
        Components:
        - On-time delivery rate (50% of delivery score)
        - Delay penalty (25% of delivery score)  
        - Consistency (25% of delivery score)
        """
        if total_deliveries == 0:
            return SupplierScore(
                score=50.0,
                max_score=100.0,
                weight=self.weights['delivery'],
                details={'message': 'No delivery history'},
                interpretation='Insufficient data for delivery scoring'
            )
        
        # On-time delivery rate (50 points max)
        otd_rate = on_time_deliveries / total_deliveries
        otd_score = otd_rate * 50
        
        # Delay penalty (25 points max) - Lose points for delays
        # No delay = 25 points, 1 day avg delay = 20 points, etc.
        delay_penalty = min(avg_delay_days * 5, 25)
        delay_score = 25 - delay_penalty
        
        # Consistency (25 points max) - Lower variance is better
        # Variance of 0 = 25 points, high variance = 0 points
        consistency_penalty = min(lead_time_variance * 10, 25)
        consistency_score = 25 - consistency_penalty
        
        total_score = otd_score + delay_score + consistency_score
        
        # Interpretation
        if total_score >= 85:
            interpretation = "Excellent delivery performance"
        elif total_score >= 70:
            interpretation = "Good delivery, minor improvements possible"
        elif total_score >= 50:
            interpretation = "Acceptable but needs monitoring"
        else:
            interpretation = "Poor delivery - consider alternatives"
        
        return SupplierScore(
            score=round(total_score, 1),
            max_score=100.0,
            weight=self.weights['delivery'],
            details={
                'on_time_rate': f"{otd_rate*100:.1f}%",
                'on_time_deliveries': on_time_deliveries,
                'total_deliveries': total_deliveries,
                'avg_delay_days': round(avg_delay_days, 1),
                'lead_time_variance': round(lead_time_variance, 2),
                'otd_score': round(otd_score, 1),
                'delay_score': round(delay_score, 1),
                'consistency_score': round(consistency_score, 1)
            },
            interpretation=interpretation
        )
    
    def calculate_quality_score(self,
                               defect_rate: float,
                               return_rate: float = 0,
                               quality_incidents: int = 0,
                               total_units: int = 1000) -> SupplierScore:
        """
        Score supplier on product quality.
        
        Components:
        - Defect rate score (50% of quality score)
        - Return rate score (30% of quality score)
        - Incident penalty (20% of quality score)
        """
        # Defect rate score (50 points max)
        # 0% defects = 50, 1% = 40, 5% = 0
        defect_score = max(0, 50 - (defect_rate * 100 * 10))
        
        # Return rate score (30 points max)
        # 0% returns = 30, 1% = 25, 6% = 0
        return_score = max(0, 30 - (return_rate * 100 * 5))
        
        # Incident penalty (20 points max)
        # 0 incidents = 20, each incident = -4 points
        incident_penalty = min(quality_incidents * 4, 20)
        incident_score = 20 - incident_penalty
        
        total_score = defect_score + return_score + incident_score
        
        # Interpretation
        if total_score >= 85:
            interpretation = "Excellent quality standards"
        elif total_score >= 70:
            interpretation = "Good quality with minor issues"
        elif total_score >= 50:
            interpretation = "Quality concerns - implement inspection"
        else:
            interpretation = "Serious quality issues - immediate action needed"
        
        return SupplierScore(
            score=round(total_score, 1),
            max_score=100.0,
            weight=self.weights['quality'],
            details={
                'defect_rate': f"{defect_rate*100:.2f}%",
                'return_rate': f"{return_rate*100:.2f}%",
                'quality_incidents': quality_incidents,
                'total_units_evaluated': total_units,
                'defect_score': round(defect_score, 1),
                'return_score': round(return_score, 1),
                'incident_score': round(incident_score, 1)
            },
            interpretation=interpretation
        )
    
    def calculate_price_score(self,
                             avg_unit_price: float,
                             market_avg_price: float,
                             price_change_pct: float = 0,
                             bulk_discount_available: bool = False) -> SupplierScore:
        """
        Score supplier on pricing.
        
        Components:
        - Price competitiveness (60% of price score)
        - Price stability (25% of price score)
        - Discount availability (15% of price score)
        """
        # Price competitiveness (60 points max)
        if market_avg_price > 0:
            price_ratio = avg_unit_price / market_avg_price
            if price_ratio <= 0.85:
                competitive_score = 60  # Significantly below market
            elif price_ratio <= 0.95:
                competitive_score = 55  # Below market
            elif price_ratio <= 1.05:
                competitive_score = 45  # At market
            elif price_ratio <= 1.15:
                competitive_score = 30  # Above market
            else:
                competitive_score = max(0, 60 - (price_ratio - 0.85) * 50)
        else:
            competitive_score = 45  # No market data
        
        # Price stability (25 points max)
        # 0% change = 25, 5% change = 15, 10%+ change = 0
        stability_penalty = min(abs(price_change_pct) * 2.5, 25)
        stability_score = 25 - stability_penalty
        
        # Discount availability (15 points max)
        discount_score = 15 if bulk_discount_available else 5
        
        total_score = competitive_score + stability_score + discount_score
        
        # Price comparison interpretation
        if market_avg_price > 0:
            diff_pct = ((avg_unit_price / market_avg_price) - 1) * 100
            price_comparison = f"{diff_pct:+.1f}% vs market"
        else:
            price_comparison = "No market comparison available"
        
        # Interpretation
        if total_score >= 80:
            interpretation = "Excellent pricing - competitive advantage"
        elif total_score >= 60:
            interpretation = "Fair pricing within market range"
        elif total_score >= 40:
            interpretation = "Above market - negotiate or seek alternatives"
        else:
            interpretation = "Expensive - strongly consider alternatives"
        
        return SupplierScore(
            score=round(total_score, 1),
            max_score=100.0,
            weight=self.weights['price'],
            details={
                'avg_unit_price': round(avg_unit_price, 2),
                'market_avg_price': round(market_avg_price, 2),
                'vs_market': price_comparison,
                'price_change_pct': f"{price_change_pct:+.1f}%",
                'bulk_discount_available': bulk_discount_available,
                'competitive_score': round(competitive_score, 1),
                'stability_score': round(stability_score, 1),
                'discount_score': round(discount_score, 1)
            },
            interpretation=interpretation
        )
    
    def calculate_responsiveness_score(self,
                                       avg_response_hours: float = 24,
                                       issue_resolution_days: float = 3,
                                       communication_rating: int = 3) -> SupplierScore:
        """
        Score supplier on responsiveness and communication.
        
        Components:
        - Response time (40% of responsiveness score)
        - Issue resolution (35% of responsiveness score)
        - Communication quality (25% of responsiveness score)
        """
        # Response time (40 points max)
        # <4 hours = 40, 24 hours = 25, 48+ hours = 0
        if avg_response_hours <= 4:
            response_score = 40
        elif avg_response_hours <= 8:
            response_score = 35
        elif avg_response_hours <= 24:
            response_score = 25
        elif avg_response_hours <= 48:
            response_score = 15
        else:
            response_score = max(0, 40 - avg_response_hours)
        
        # Issue resolution (35 points max)
        # <1 day = 35, 3 days = 25, 7+ days = 0
        if issue_resolution_days <= 1:
            resolution_score = 35
        elif issue_resolution_days <= 3:
            resolution_score = 28
        elif issue_resolution_days <= 5:
            resolution_score = 18
        else:
            resolution_score = max(0, 35 - issue_resolution_days * 4)
        
        # Communication rating (25 points max)
        # Rating 1-5, convert to 0-25 scale
        communication_score = min(25, (communication_rating / 5) * 25)
        
        total_score = response_score + resolution_score + communication_score
        
        # Interpretation
        if total_score >= 80:
            interpretation = "Excellent communication and responsiveness"
        elif total_score >= 60:
            interpretation = "Good responsiveness with room for improvement"
        elif total_score >= 40:
            interpretation = "Slow responses - may cause operational delays"
        else:
            interpretation = "Poor communication - significant concern"
        
        return SupplierScore(
            score=round(total_score, 1),
            max_score=100.0,
            weight=self.weights['responsiveness'],
            details={
                'avg_response_hours': round(avg_response_hours, 1),
                'issue_resolution_days': round(issue_resolution_days, 1),
                'communication_rating': f"{communication_rating}/5",
                'response_score': round(response_score, 1),
                'resolution_score': round(resolution_score, 1),
                'communication_score': round(communication_score, 1)
            },
            interpretation=interpretation
        )
    
    def determine_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        for grade, threshold in self.grade_thresholds.items():
            if score >= threshold:
                return grade
        return 'F'
    
    def determine_risk_level(self, score: float) -> str:
        """Convert score to risk level."""
        for level, threshold in self.risk_thresholds.items():
            if score >= threshold:
                return level
        return 'Critical'
    
    def generate_recommendations(self,
                                delivery: SupplierScore,
                                quality: SupplierScore,
                                price: SupplierScore,
                                responsiveness: SupplierScore,
                                overall_score: float) -> Tuple[List[str], List[str], List[str]]:
        """Generate recommendations, risk factors, and strengths."""
        recommendations = []
        risk_factors = []
        strengths = []
        
        # Delivery analysis
        if delivery.score < 60:
            recommendations.append("Negotiate stricter delivery SLAs with penalties")
            risk_factors.append(f"Delivery reliability at {delivery.score:.0f}% - high delay risk")
        elif delivery.score >= 85:
            strengths.append("Consistently reliable deliveries")
        
        # Quality analysis
        if quality.score < 60:
            recommendations.append("Implement incoming quality inspection")
            recommendations.append("Request quality improvement plan from supplier")
            risk_factors.append(f"Quality score {quality.score:.0f}% - defects may impact operations")
        elif quality.score >= 85:
            strengths.append("Excellent product quality")
        
        # Price analysis
        if price.score < 50:
            recommendations.append("Explore alternative suppliers for cost reduction")
            recommendations.append("Negotiate bulk discounts or long-term pricing")
            risk_factors.append("Pricing above market average")
        elif price.score >= 75:
            strengths.append("Competitive pricing")
        
        # Responsiveness analysis
        if responsiveness.score < 50:
            recommendations.append("Establish clearer communication channels")
            recommendations.append("Set response time expectations in contract")
            risk_factors.append("Slow response times may delay issue resolution")
        elif responsiveness.score >= 80:
            strengths.append("Excellent communication and support")
        
        # Overall recommendations
        if overall_score < 60:
            recommendations.insert(0, "⚠️ PRIORITY: Develop backup supplier relationship")
        
        if overall_score >= 85:
            recommendations.append("Consider strategic partnership for preferred pricing")
        
        return recommendations, risk_factors, strengths
    
    def generate_scorecard(self,
                          supplier_name: str,
                          supplier_id: str = None,
                          delivery_metrics: Dict = None,
                          quality_metrics: Dict = None,
                          price_metrics: Dict = None,
                          responsiveness_metrics: Dict = None,
                          previous_score: float = None) -> SupplierScorecard:
        """
        Generate comprehensive supplier scorecard.
        
        Args:
            supplier_name: Name of supplier
            supplier_id: Unique identifier
            delivery_metrics: Dict with on_time_deliveries, total_deliveries, etc.
            quality_metrics: Dict with defect_rate, return_rate, etc.
            price_metrics: Dict with avg_unit_price, market_avg_price, etc.
            responsiveness_metrics: Dict with avg_response_hours, etc.
            previous_score: Previous overall score for trend calculation
        """
        # Set defaults if metrics not provided
        delivery_metrics = delivery_metrics or {
            'on_time_deliveries': 0, 'total_deliveries': 0
        }
        quality_metrics = quality_metrics or {
            'defect_rate': 0.01, 'return_rate': 0
        }
        price_metrics = price_metrics or {
            'avg_unit_price': 100, 'market_avg_price': 100
        }
        responsiveness_metrics = responsiveness_metrics or {}
        
        # Calculate component scores
        delivery = self.calculate_delivery_score(**delivery_metrics)
        quality = self.calculate_quality_score(**quality_metrics)
        price = self.calculate_price_score(**price_metrics)
        responsiveness = self.calculate_responsiveness_score(**responsiveness_metrics)
        
        # Calculate weighted overall score
        overall_score = (
            delivery.score * delivery.weight +
            quality.score * quality.weight +
            price.score * price.weight +
            responsiveness.score * responsiveness.weight
        )
        
        # Determine grade and risk
        grade = self.determine_grade(overall_score)
        risk_level = self.determine_risk_level(overall_score)
        
        # Generate recommendations
        recommendations, risk_factors, strengths = self.generate_recommendations(
            delivery, quality, price, responsiveness, overall_score
        )
        
        # Determine trend
        if previous_score is not None:
            if overall_score > previous_score + 5:
                trend = "improving"
            elif overall_score < previous_score - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "new"
        
        return SupplierScorecard(
            supplier_name=supplier_name,
            supplier_id=supplier_id or supplier_name.lower().replace(' ', '_'),
            reliability_score=round(overall_score, 1),
            overall_grade=grade,
            risk_level=risk_level,
            delivery_score=delivery.score,
            quality_score=quality.score,
            price_score=price.score,
            responsiveness_score=responsiveness.score,
            delivery_details=delivery.details,
            quality_details=quality.details,
            price_details=price.details,
            responsiveness_details=responsiveness.details,
            recommendations=recommendations,
            risk_factors=risk_factors,
            strengths=strengths,
            trend=trend,
            last_updated=datetime.now().isoformat()
        )


def score_supplier(
    supplier_name: str,
    defect_rate: float,
    lead_time_days: int,
    on_time_rate: float = 0.9,
    unit_cost: float = 100,
    market_avg_cost: float = 100
) -> Dict:
    """
    Convenience function for quick supplier scoring.
    
    Returns:
        Dict with supplier scorecard
    """
    scorer = SupplierReliabilityScorer()
    
    try:
        # Calculate metrics from simple inputs
        total_deliveries = 100  # Assumed for calculation
        on_time_deliveries = int(total_deliveries * on_time_rate)
        
        scorecard = scorer.generate_scorecard(
            supplier_name=supplier_name,
            delivery_metrics={
                'on_time_deliveries': on_time_deliveries,
                'total_deliveries': total_deliveries,
                'avg_delay_days': (1 - on_time_rate) * lead_time_days * 0.5,
                'lead_time_variance': lead_time_days * 0.15
            },
            quality_metrics={
                'defect_rate': defect_rate,
                'return_rate': defect_rate * 0.5,
                'quality_incidents': int(defect_rate * 10)
            },
            price_metrics={
                'avg_unit_price': unit_cost,
                'market_avg_price': market_avg_cost,
                'price_change_pct': 0,
                'bulk_discount_available': True
            }
        )
        
        return {
            'success': True,
            **asdict(scorecard)
        }
    except Exception as e:
        logger.error(f"Supplier scoring failed for {supplier_name}: {e}")
        return {
            'success': False,
            'supplier_name': supplier_name,
            'error': str(e)
        }
