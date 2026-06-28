# src/inventory_optimizer.py
"""
OptiStock: Dynamic Inventory Optimization Engine
Calculates safety stock, reorder points, EOQ with explainable formulas.
Detects slow-moving, dead stock, and overstock situations.
"""

import numpy as np
from scipy import stats
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class StockStatus(Enum):
    """Inventory health classification."""
    HEALTHY = "healthy"
    LOW_STOCK = "low_stock"
    OVERSTOCK = "overstock"
    SLOW_MOVING = "slow_moving"
    DEAD_STOCK = "dead_stock"
    STOCKOUT_RISK = "stockout_risk"
    CRITICAL = "critical"


@dataclass
class InventoryMetrics:
    """Comprehensive inventory health metrics with explanations."""
    sku: str
    product_name: str
    
    # Calculated values
    safety_stock: int
    reorder_point: int
    economic_order_quantity: int
    
    # Health indicators
    days_of_supply: float
    inventory_turnover: float
    stock_status: str  # StockStatus value
    status_reason: str
    
    # Risk metrics
    overstock_units: int
    stockout_probability: float
    
    # Cost metrics
    holding_cost_daily: float
    potential_stockout_cost: float
    
    # Recommendations
    units_to_order: int
    order_urgency: str  # "immediate", "soon", "not_needed"
    
    # Explanations
    safety_stock_explanation: Dict
    reorder_point_explanation: Dict
    eoq_explanation: Dict


@dataclass
class DemandStatistics:
    """Demand statistics for calculations."""
    avg_daily_demand: float
    std_daily_demand: float
    avg_demand_during_lt: float
    std_demand_during_lt: float
    coefficient_of_variation: float
    max_daily_demand: float
    min_daily_demand: float


class InventoryOptimizer:
    """
    Dynamic inventory optimization with explainable calculations.
    Implements service-level based safety stock and EOQ models.
    
    Key Features:
    - Dynamic safety stock based on demand variability
    - Service-level driven calculations (default 95%)
    - Lead time uncertainty handling
    - Stock classification (healthy, overstock, dead stock, etc.)
    - Explainable formulas for each calculation
    """
    
    def __init__(self, 
                 service_level: float = 0.95,
                 holding_cost_rate: float = 0.25,
                 stockout_cost_multiplier: float = 2.0,
                 order_cost_default: float = 50.0):
        """
        Initialize optimizer with cost parameters.
        
        Args:
            service_level: Target fill rate (0.95 = 95%)
            holding_cost_rate: Annual holding cost as % of item value
            stockout_cost_multiplier: Stockout cost relative to item cost
            order_cost_default: Default cost per order placed
        """
        self.service_level = service_level
        self.holding_cost_rate = holding_cost_rate
        self.stockout_cost_multiplier = stockout_cost_multiplier
        self.order_cost_default = order_cost_default
        
        # Z-score for service level (1.645 for 95%)
        self.z_score = stats.norm.ppf(service_level)
        
    def calculate_demand_statistics(self, 
                                   daily_demands: List[float],
                                   lead_time_days: int,
                                   lead_time_std: float = None) -> DemandStatistics:
        """
        Calculate demand statistics during lead time.
        
        Args:
            daily_demands: Historical daily demand values
            lead_time_days: Average supplier lead time
            lead_time_std: Standard deviation of lead time (optional)
            
        Returns:
            DemandStatistics with calculated values
        """
        demands = np.array([max(0, d) for d in daily_demands])  # Ensure non-negative
        
        if len(demands) == 0:
            demands = np.array([0])
        
        avg_daily_demand = float(np.mean(demands))
        std_daily_demand = float(np.std(demands)) if len(demands) > 1 else avg_daily_demand * 0.3
        
        # Demand during lead time
        avg_demand_during_lt = avg_daily_demand * lead_time_days
        
        # Combined variance (demand + lead time uncertainty)
        if lead_time_std and lead_time_std > 0:
            # When lead time is variable: Var = LT*σ²_d + d̄²*σ²_LT
            variance_during_lt = (
                lead_time_days * (std_daily_demand ** 2) +
                (avg_daily_demand ** 2) * (lead_time_std ** 2)
            )
        else:
            # Fixed lead time: Var = LT * σ²_d
            variance_during_lt = lead_time_days * (std_daily_demand ** 2)
        
        std_demand_during_lt = float(np.sqrt(max(0, variance_during_lt)))
        
        # Coefficient of variation (demand variability indicator)
        cv = std_daily_demand / avg_daily_demand if avg_daily_demand > 0 else 0
        
        return DemandStatistics(
            avg_daily_demand=round(avg_daily_demand, 2),
            std_daily_demand=round(std_daily_demand, 2),
            avg_demand_during_lt=round(avg_demand_during_lt, 2),
            std_demand_during_lt=round(std_demand_during_lt, 2),
            coefficient_of_variation=round(cv, 3),
            max_daily_demand=float(np.max(demands)) if len(demands) > 0 else 0,
            min_daily_demand=float(np.min(demands)) if len(demands) > 0 else 0
        )
    
    def calculate_safety_stock(self, demand_stats: DemandStatistics) -> Tuple[int, Dict]:
        """
        Calculate safety stock with explainable formula.
        
        Formula: Safety Stock = Z × σ_LT
        Where:
            Z = Service level z-score (1.645 for 95%)
            σ_LT = Standard deviation of demand during lead time
        """
        safety_stock = self.z_score * demand_stats.std_demand_during_lt
        safety_stock = max(1, int(np.ceil(safety_stock)))  # Minimum 1 unit
        
        explanation = {
            'formula': 'Safety Stock = Z × σ_LT',
            'components': {
                'z_score': round(self.z_score, 3),
                'service_level': f"{self.service_level * 100:.0f}%",
                'demand_std_during_lt': demand_stats.std_demand_during_lt
            },
            'calculation': f"{round(self.z_score, 2)} × {demand_stats.std_demand_during_lt:.1f} = {safety_stock}",
            'interpretation': f"Buffer of {safety_stock} units provides {self.service_level*100:.0f}% protection against demand variability during lead time"
        }
        
        return safety_stock, explanation
    
    def calculate_reorder_point(self, 
                               demand_stats: DemandStatistics,
                               safety_stock: int,
                               lead_time_days: int) -> Tuple[int, Dict]:
        """
        Calculate reorder point with explainable formula.
        
        Formula: ROP = (D̄ × LT) + SS
        Where:
            D̄ = Average daily demand
            LT = Lead time in days
            SS = Safety stock
        """
        demand_during_lt = demand_stats.avg_daily_demand * lead_time_days
        rop = demand_during_lt + safety_stock
        rop = max(1, int(np.ceil(rop)))
        
        explanation = {
            'formula': 'ROP = (D̄ × LT) + SS',
            'components': {
                'avg_daily_demand': demand_stats.avg_daily_demand,
                'lead_time_days': lead_time_days,
                'safety_stock': safety_stock,
                'demand_during_lead_time': round(demand_during_lt, 1)
            },
            'calculation': f"({demand_stats.avg_daily_demand:.1f} × {lead_time_days}) + {safety_stock} = {rop}",
            'interpretation': f"Place order when inventory reaches {rop} units to avoid stockout"
        }
        
        return rop, explanation
    
    def calculate_eoq(self,
                     annual_demand: float,
                     unit_cost: float,
                     order_cost: float = None) -> Tuple[int, Dict]:
        """
        Calculate Economic Order Quantity.
        
        Formula: EOQ = √((2 × D × S) / H)
        Where:
            D = Annual demand
            S = Order/Setup cost
            H = Holding cost per unit per year
        """
        order_cost = order_cost or self.order_cost_default
        holding_cost = unit_cost * self.holding_cost_rate
        
        if holding_cost <= 0 or annual_demand <= 0:
            return 1, {'error': 'Invalid inputs for EOQ calculation', 'formula': 'N/A'}
        
        eoq = np.sqrt((2 * annual_demand * order_cost) / holding_cost)
        eoq = max(1, int(np.ceil(eoq)))
        
        orders_per_year = annual_demand / eoq if eoq > 0 else 0
        
        explanation = {
            'formula': 'EOQ = √((2 × D × S) / H)',
            'components': {
                'annual_demand': int(annual_demand),
                'order_cost': order_cost,
                'holding_cost_per_unit': round(holding_cost, 2),
                'holding_cost_rate': f"{self.holding_cost_rate * 100:.0f}%"
            },
            'calculation': f"√((2 × {int(annual_demand)} × {order_cost}) / {holding_cost:.2f}) = {eoq}",
            'optimal_orders_per_year': round(orders_per_year, 1),
            'interpretation': f"Order {eoq} units at a time ({round(orders_per_year, 1)} orders/year) to minimize total costs"
        }
        
        return eoq, explanation
    
    def classify_stock_status(self,
                             current_stock: int,
                             safety_stock: int,
                             reorder_point: int,
                             avg_daily_demand: float,
                             days_since_last_sale: int = None) -> Tuple[StockStatus, str]:
        """
        Classify inventory status with business context.
        
        Classifications:
        - CRITICAL: Stock is zero or will deplete before delivery
        - STOCKOUT_RISK: Below safety stock
        - LOW_STOCK: Below reorder point but above safety stock
        - HEALTHY: Normal stock levels
        - OVERSTOCK: More than 60 days of supply
        - SLOW_MOVING: Low turnover (30-90 days no sale)
        - DEAD_STOCK: No sales in 90+ days
        """
        days_of_supply = current_stock / avg_daily_demand if avg_daily_demand > 0 else float('inf')
        
        # Check for dead/slow stock first
        if days_since_last_sale is not None:
            if days_since_last_sale > 90:
                return StockStatus.DEAD_STOCK, f"No sales in {days_since_last_sale} days - consider clearance"
            elif days_since_last_sale > 30:
                return StockStatus.SLOW_MOVING, f"Only {round(30/days_since_last_sale, 1)} sales/month avg"
        
        # Stock level classifications
        if current_stock == 0:
            return StockStatus.CRITICAL, "Out of stock! Immediate action required"
        
        if current_stock < safety_stock:
            return StockStatus.STOCKOUT_RISK, f"Stock ({current_stock}) below safety level ({safety_stock})"
        
        if current_stock <= reorder_point:
            return StockStatus.LOW_STOCK, f"Stock at reorder point - place order now"
        
        if days_of_supply > 90:
            excess = current_stock - (reorder_point * 2)
            return StockStatus.OVERSTOCK, f"{int(days_of_supply)} days of supply - excess of ~{max(0, excess)} units"
        
        if days_of_supply > 60:
            return StockStatus.OVERSTOCK, f"{int(days_of_supply)} days of supply (above 60-day threshold)"
        
        return StockStatus.HEALTHY, f"{int(days_of_supply)} days of supply - stock levels optimal"
    
    def calculate_stockout_probability(self,
                                      current_stock: int,
                                      demand_stats: DemandStatistics,
                                      days_until_delivery: int) -> float:
        """
        Calculate probability of stockout before next delivery.
        Uses normal distribution CDF.
        
        P(Stockout) = P(Demand > Current Stock) = 1 - Φ((Stock - μ) / σ)
        """
        if days_until_delivery <= 0:
            return 0.0
        
        expected_demand = demand_stats.avg_daily_demand * days_until_delivery
        std_demand = demand_stats.std_daily_demand * np.sqrt(days_until_delivery)
        
        if std_demand == 0:
            return 0.0 if current_stock >= expected_demand else 1.0
        
        # P(Demand > Current Stock)
        z = (current_stock - expected_demand) / std_demand
        stockout_prob = 1 - stats.norm.cdf(z)
        
        return round(min(1.0, max(0.0, stockout_prob)), 4)
    
    def calculate_order_urgency(self,
                               status: StockStatus,
                               days_of_supply: float,
                               lead_time_days: int) -> str:
        """Determine order urgency based on status and timing."""
        
        if status in [StockStatus.CRITICAL, StockStatus.STOCKOUT_RISK]:
            return "immediate"
        
        if status == StockStatus.LOW_STOCK:
            return "immediate" if days_of_supply < lead_time_days else "soon"
        
        if days_of_supply < lead_time_days * 1.5:
            return "soon"
        
        return "not_needed"
    
    def full_analysis(self,
                     sku: str,
                     product_name: str,
                     current_stock: int,
                     daily_demands: List[float],
                     lead_time_days: int,
                     unit_cost: float,
                     lead_time_std: float = None,
                     order_cost: float = None,
                     days_since_last_sale: int = None) -> InventoryMetrics:
        """
        Run complete inventory optimization analysis.
        
        Args:
            sku: Product identifier
            product_name: Product name
            current_stock: Current inventory level
            daily_demands: List of historical daily demand values
            lead_time_days: Average supplier lead time
            unit_cost: Cost per unit
            lead_time_std: Lead time standard deviation (optional)
            order_cost: Cost per order (optional)
            days_since_last_sale: Days since last sale (optional)
            
        Returns:
            InventoryMetrics with complete analysis
        """
        # Default lead time std if not provided
        if lead_time_std is None:
            lead_time_std = lead_time_days * 0.2  # Assume 20% variability
        
        # Calculate demand statistics
        demand_stats = self.calculate_demand_statistics(
            daily_demands, lead_time_days, lead_time_std
        )
        
        # Safety stock
        safety_stock, ss_explanation = self.calculate_safety_stock(demand_stats)
        
        # Reorder point
        reorder_point, rop_explanation = self.calculate_reorder_point(
            demand_stats, safety_stock, lead_time_days
        )
        
        # EOQ
        annual_demand = demand_stats.avg_daily_demand * 365
        eoq, eoq_explanation = self.calculate_eoq(
            annual_demand, unit_cost, order_cost
        )
        
        # Stock status classification
        status, status_reason = self.classify_stock_status(
            current_stock, safety_stock, reorder_point,
            demand_stats.avg_daily_demand, days_since_last_sale
        )
        
        # Days of supply
        days_of_supply = (current_stock / demand_stats.avg_daily_demand 
                         if demand_stats.avg_daily_demand > 0 else 999)
        
        # Inventory turnover (annual)
        turnover = annual_demand / current_stock if current_stock > 0 else 0
        
        # Overstock calculation
        max_reasonable_stock = reorder_point + eoq
        overstock = max(0, current_stock - max_reasonable_stock)
        
        # Stockout probability (assuming order placed now)
        stockout_prob = self.calculate_stockout_probability(
            current_stock, demand_stats, lead_time_days
        )
        
        # Cost calculations
        holding_cost_daily = (current_stock * unit_cost * self.holding_cost_rate) / 365
        potential_stockout_cost = (stockout_prob * demand_stats.avg_daily_demand * 
                                  unit_cost * self.stockout_cost_multiplier * lead_time_days)
        
        # Order recommendation
        urgency = self.calculate_order_urgency(status, days_of_supply, lead_time_days)
        
        if status in [StockStatus.CRITICAL, StockStatus.STOCKOUT_RISK, StockStatus.LOW_STOCK]:
            units_to_order = max(eoq, reorder_point + safety_stock - current_stock)
        elif status == StockStatus.OVERSTOCK:
            units_to_order = 0
        else:
            units_to_order = 0
        
        return InventoryMetrics(
            sku=sku,
            product_name=product_name,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            economic_order_quantity=eoq,
            days_of_supply=round(days_of_supply, 1),
            inventory_turnover=round(turnover, 2),
            stock_status=status.value,
            status_reason=status_reason,
            overstock_units=overstock,
            stockout_probability=stockout_prob,
            holding_cost_daily=round(holding_cost_daily, 2),
            potential_stockout_cost=round(potential_stockout_cost, 2),
            units_to_order=max(0, int(units_to_order)),
            order_urgency=urgency,
            safety_stock_explanation=ss_explanation,
            reorder_point_explanation=rop_explanation,
            eoq_explanation=eoq_explanation
        )


def analyze_inventory_item(
    sku: str,
    product_name: str,
    current_stock: int,
    daily_demands: List[float],
    lead_time_days: int,
    unit_cost: float,
    service_level: float = 0.95
) -> Dict:
    """
    Convenience function for single item analysis.
    
    Returns:
        Dict with complete inventory analysis
    """
    optimizer = InventoryOptimizer(service_level=service_level)
    
    try:
        result = optimizer.full_analysis(
            sku=sku,
            product_name=product_name,
            current_stock=current_stock,
            daily_demands=daily_demands,
            lead_time_days=lead_time_days,
            unit_cost=unit_cost
        )
        
        return {
            'success': True,
            **asdict(result)
        }
    except Exception as e:
        logger.error(f"Inventory analysis failed for {sku}: {e}")
        return {
            'success': False,
            'sku': sku,
            'error': str(e)
        }
