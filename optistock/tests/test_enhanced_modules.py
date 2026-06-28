# tests/test_enhanced_modules.py
"""
OptiStock: Test Suite for Enhanced AI Modules
Tests for advanced forecasting, inventory optimization, XAI, and more.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_sales_data():
    """Generate sample sales data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=90, freq='D')
    # Simulate seasonal pattern with noise
    np.random.seed(42)
    base_demand = 100
    seasonal = 20 * np.sin(np.arange(90) * 2 * np.pi / 7)  # Weekly pattern
    noise = np.random.normal(0, 10, 90)
    values = base_demand + seasonal + noise
    values = np.maximum(values, 0).astype(int)
    
    return pd.DataFrame({
        'ds': dates,
        'y': values
    })


@pytest.fixture
def sample_inventory_item():
    """Sample inventory item for testing."""
    return {
        'sku': 'TEST-001',
        'product_name': 'Test Product',
        'category': 'Electronics',
        'current_stock': 150,
        'cost_per_unit': 25.99,
        'supplier': 'Test Supplier Inc',
        'defect_rate': 0.02,
        'lead_time_days': 7
    }


@pytest.fixture
def sample_daily_demands():
    """Sample daily demand history."""
    np.random.seed(42)
    return [int(x) for x in np.random.normal(50, 15, 30).clip(10, 100)]


# =============================================================================
# ADVANCED FORECASTING TESTS
# =============================================================================

class TestAdvancedForecasting:
    """Tests for the advanced forecasting module."""
    
    def test_import_module(self):
        """Test that the module can be imported."""
        from src.advanced_forecasting import HybridDemandForecaster, run_hybrid_forecast
        assert HybridDemandForecaster is not None
        assert run_hybrid_forecast is not None
    
    def test_forecaster_initialization(self):
        """Test forecaster initialization."""
        from src.advanced_forecasting import HybridDemandForecaster
        
        forecaster = HybridDemandForecaster(forecast_days=14)
        assert forecaster.forecast_days == 14
        assert forecaster.prophet_model is None
        assert forecaster.is_fitted is False
    
    def test_forecaster_with_sales_data(self, sample_sales_data):
        """Test forecasting with sample data."""
        from src.advanced_forecasting import HybridDemandForecaster
        
        forecaster = HybridDemandForecaster(forecast_days=7)
        
        # This should work even if XGBoost is not installed
        try:
            result = forecaster.fit(sample_sales_data)
            assert forecaster.is_fitted == True
        except ImportError:
            # XGBoost not installed, skip
            pytest.skip("XGBoost not installed")
    
    def test_convenience_function(self, sample_sales_data):
        """Test the convenience function."""
        from src.advanced_forecasting import run_hybrid_forecast
        
        result = run_hybrid_forecast(
            sales_df=sample_sales_data,
            sku='TEST-001',
            forecast_days=7
        )
        
        assert isinstance(result, dict)
        assert 'success' in result
    
    def test_anomaly_detection(self, sample_sales_data):
        """Test anomaly detection method."""
        from src.advanced_forecasting import HybridDemandForecaster
        
        forecaster = HybridDemandForecaster()
        anomalies = forecaster._detect_anomalies(sample_sales_data)
        
        assert isinstance(anomalies, list)


# =============================================================================
# INVENTORY OPTIMIZER TESTS
# =============================================================================

class TestInventoryOptimizer:
    """Tests for the inventory optimization module."""
    
    def test_import_module(self):
        """Test module import."""
        from src.inventory_optimizer import InventoryOptimizer, analyze_inventory_item, StockStatus
        assert InventoryOptimizer is not None
        assert StockStatus is not None
    
    def test_optimizer_initialization(self):
        """Test optimizer initialization."""
        from src.inventory_optimizer import InventoryOptimizer
        
        optimizer = InventoryOptimizer(service_level=0.95)
        assert optimizer.service_level == 0.95
        assert optimizer.z_score > 0
    
    def test_safety_stock_calculation(self, sample_daily_demands):
        """Test safety stock calculation."""
        from src.inventory_optimizer import InventoryOptimizer
        
        optimizer = InventoryOptimizer(service_level=0.95)
        result = optimizer.calculate_safety_stock(
            daily_demands=sample_daily_demands,
            lead_time_days=7
        )
        
        assert isinstance(result, dict)
        assert 'safety_stock' in result
        assert result['safety_stock'] > 0
    
    def test_reorder_point_calculation(self, sample_daily_demands):
        """Test reorder point calculation."""
        from src.inventory_optimizer import InventoryOptimizer
        
        optimizer = InventoryOptimizer()
        result = optimizer.calculate_reorder_point(
            daily_demands=sample_daily_demands,
            lead_time_days=7,
            safety_stock=50
        )
        
        assert isinstance(result, dict)
        assert 'reorder_point' in result
        assert result['reorder_point'] > 50  # Should be > safety stock
    
    def test_stock_status_determination(self, sample_daily_demands):
        """Test stock status determination."""
        from src.inventory_optimizer import InventoryOptimizer, StockStatus
        
        optimizer = InventoryOptimizer()
        
        # Test low stock
        status, reason = optimizer._determine_stock_status(
            current_stock=30,
            reorder_point=100,
            safety_stock=50,
            days_of_supply=3,
            avg_daily_demand=50
        )
        assert status in [StockStatus.LOW_STOCK, StockStatus.CRITICAL, StockStatus.STOCKOUT_RISK]
        
        # Test healthy stock
        status2, reason2 = optimizer._determine_stock_status(
            current_stock=200,
            reorder_point=100,
            safety_stock=50,
            days_of_supply=30,
            avg_daily_demand=50
        )
        assert status2 == StockStatus.HEALTHY
    
    def test_convenience_function(self, sample_daily_demands):
        """Test the convenience function."""
        from src.inventory_optimizer import analyze_inventory_item
        
        result = analyze_inventory_item(
            sku='TEST-001',
            product_name='Test Product',
            current_stock=150,
            daily_demands=sample_daily_demands,
            lead_time_days=7,
            unit_cost=25.99
        )
        
        assert isinstance(result, dict)
        assert result['success'] == True
        assert 'safety_stock' in result
        assert 'reorder_point' in result
        assert 'stock_status' in result


# =============================================================================
# SUPPLIER SCORING TESTS
# =============================================================================

class TestSupplierScoring:
    """Tests for the supplier scoring module."""
    
    def test_import_module(self):
        """Test module import."""
        from src.supplier_scoring import SupplierReliabilityScorer, score_supplier
        assert SupplierReliabilityScorer is not None
        assert score_supplier is not None
    
    def test_scorer_initialization(self):
        """Test scorer initialization."""
        from src.supplier_scoring import SupplierReliabilityScorer
        
        scorer = SupplierReliabilityScorer()
        assert scorer is not None
    
    def test_score_excellent_supplier(self):
        """Test scoring an excellent supplier."""
        from src.supplier_scoring import SupplierReliabilityScorer
        
        scorer = SupplierReliabilityScorer()
        scorecard = scorer.generate_scorecard(
            supplier_name="Excellent Corp",
            defect_rate=0.001,
            lead_time_days=3,
            on_time_rate=0.99,
            unit_cost=100,
            market_avg_cost=120
        )
        
        assert scorecard.reliability_score > 80
        assert scorecard.overall_grade in ['A', 'B']
        assert scorecard.risk_level == 'low'
    
    def test_score_poor_supplier(self):
        """Test scoring a poor supplier."""
        from src.supplier_scoring import SupplierReliabilityScorer
        
        scorer = SupplierReliabilityScorer()
        scorecard = scorer.generate_scorecard(
            supplier_name="Poor Quality Inc",
            defect_rate=0.15,
            lead_time_days=21,
            on_time_rate=0.60,
            unit_cost=150,
            market_avg_cost=100
        )
        
        assert scorecard.reliability_score < 50
        assert scorecard.overall_grade in ['D', 'F']
        assert scorecard.risk_level == 'high'
    
    def test_convenience_function(self):
        """Test the convenience function."""
        from src.supplier_scoring import score_supplier
        
        result = score_supplier(
            supplier_name="Test Supplier",
            defect_rate=0.03,
            lead_time_days=5
        )
        
        assert isinstance(result, dict)
        assert result['success'] == True
        assert 'reliability_score' in result
        assert 'recommendations' in result


# =============================================================================
# XAI ENGINE TESTS
# =============================================================================

class TestXAIEngine:
    """Tests for the explainable AI engine."""
    
    def test_import_module(self):
        """Test module import."""
        from src.xai_engine import ExplainableDecisionEngine, generate_explanation, DecisionType
        assert ExplainableDecisionEngine is not None
        assert DecisionType is not None
    
    def test_engine_initialization(self):
        """Test engine initialization."""
        from src.xai_engine import ExplainableDecisionEngine
        
        engine = ExplainableDecisionEngine()
        assert engine is not None
    
    def test_generate_explanation_restock(self):
        """Test explanation generation for restock decision."""
        from src.xai_engine import ExplainableDecisionEngine
        
        engine = ExplainableDecisionEngine()
        explanation = engine.generate_decision_explanation(
            sku='TEST-001',
            product_name='Test Product',
            current_stock=30,
            forecasted_demand=200,
            safety_stock=50,
            reorder_point=100,
            lead_time_days=7,
            unit_cost=25.99
        )
        
        assert explanation is not None
        assert explanation.decision_type.name in ['RESTOCK_URGENT', 'RESTOCK_SOON']
        assert len(explanation.primary_factors) > 0
        assert explanation.confidence > 0
    
    def test_generate_explanation_hold(self):
        """Test explanation for hold decision."""
        from src.xai_engine import ExplainableDecisionEngine
        
        engine = ExplainableDecisionEngine()
        explanation = engine.generate_decision_explanation(
            sku='TEST-002',
            product_name='Well Stocked Item',
            current_stock=500,
            forecasted_demand=100,
            safety_stock=50,
            reorder_point=100,
            lead_time_days=5,
            unit_cost=10.00
        )
        
        assert explanation.decision_type.name == 'HOLD'
        assert explanation.confidence > 0.5
    
    def test_convenience_function(self):
        """Test convenience function."""
        from src.xai_engine import generate_explanation
        
        result = generate_explanation(
            sku='TEST-001',
            product_name='Test',
            current_stock=50,
            forecasted_demand=100
        )
        
        assert isinstance(result, dict)
        assert result['success'] == True
        assert 'decision' in result
        assert 'primary_factors' in result


# =============================================================================
# NL QUERY ENGINE TESTS
# =============================================================================

class TestNLQueryEngine:
    """Tests for the natural language query engine."""
    
    def test_import_module(self):
        """Test module import."""
        from src.nl_query_engine import NaturalLanguageQueryEngine, query_inventory
        assert NaturalLanguageQueryEngine is not None
    
    def test_engine_initialization(self):
        """Test engine initialization."""
        from src.nl_query_engine import NaturalLanguageQueryEngine
        
        engine = NaturalLanguageQueryEngine()
        assert engine is not None
    
    def test_intent_classification(self):
        """Test intent classification."""
        from src.nl_query_engine import NaturalLanguageQueryEngine
        
        engine = NaturalLanguageQueryEngine()
        
        # Test stockout intent
        intent, _ = engine._classify_intent("Which products will run out soon?")
        assert intent == 'stockout_risk'
        
        # Test overstock intent
        intent2, _ = engine._classify_intent("Show me slow moving inventory")
        assert intent2 == 'overstock'
        
        # Test reorder intent
        intent3, _ = engine._classify_intent("What should I order this week?")
        assert intent3 == 'reorder'


# =============================================================================
# REPORT GENERATOR TESTS
# =============================================================================

class TestReportGenerator:
    """Tests for the report generator."""
    
    def test_import_module(self):
        """Test module import."""
        from src.report_generator import IntelligentReportGenerator, generate_report
        assert IntelligentReportGenerator is not None
    
    def test_generator_initialization(self):
        """Test generator initialization."""
        from src.report_generator import IntelligentReportGenerator
        
        generator = IntelligentReportGenerator()
        assert generator is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestModuleIntegration:
    """Integration tests for modules working together."""
    
    def test_full_analysis_pipeline(self, sample_daily_demands):
        """Test complete analysis pipeline."""
        from src.inventory_optimizer import analyze_inventory_item
        from src.xai_engine import generate_explanation
        
        # Step 1: Analyze inventory
        inventory_result = analyze_inventory_item(
            sku='INTEGRATION-001',
            product_name='Integration Test Product',
            current_stock=75,
            daily_demands=sample_daily_demands,
            lead_time_days=7,
            unit_cost=49.99
        )
        
        assert inventory_result['success']
        
        # Step 2: Generate explanation
        explanation = generate_explanation(
            sku='INTEGRATION-001',
            product_name='Integration Test Product',
            current_stock=75,
            forecasted_demand=sum(sample_daily_demands),
            safety_stock=inventory_result['safety_stock'],
            reorder_point=inventory_result['reorder_point'],
            lead_time_days=7,
            unit_cost=49.99
        )
        
        assert explanation['success']
        assert 'decision' in explanation


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
