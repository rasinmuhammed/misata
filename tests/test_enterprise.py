"""
Tests for enterprise features: benchmarks, feedback, audit, hybrid learning.
"""

import numpy as np
import pandas as pd
import pytest
import tempfile
import os


class TestBenchmark:
    """Tests for accuracy benchmarking."""
    
    def test_benchmark_normal_distribution(self):
        """Test normal distribution benchmark."""
        from misata.benchmark import AccuracyBenchmark
        
        benchmark = AccuracyBenchmark()
        
        # Generate data that should pass
        np.random.seed(42)
        data = np.random.normal(100, 20, 1000)
        
        result = benchmark.benchmark_normal(data, 100, 20, "test_col")
        
        assert result.column_name == "test_col"
        assert result.test_name == "Normal Distribution (K-S)"
        assert result.passed == True
    
    def test_benchmark_uniform_distribution(self):
        """Test uniform distribution benchmark."""
        from misata.benchmark import AccuracyBenchmark
        
        benchmark = AccuracyBenchmark()
        
        np.random.seed(42)
        data = np.random.uniform(0, 100, 1000)
        
        result = benchmark.benchmark_uniform(data, 0, 100, "test_col")
        
        assert result.passed == True
        assert result.details["in_bounds"] == True
    
    def test_benchmark_categorical(self):
        """Test categorical distribution benchmark."""
        from misata.benchmark import AccuracyBenchmark
        
        benchmark = AccuracyBenchmark()
        
        # Generate categorical with known probabilities
        np.random.seed(42)
        choices = ["A", "B", "C"]
        probs = [0.5, 0.3, 0.2]
        data = pd.Series(np.random.choice(choices, 10000, p=probs))
        
        result = benchmark.benchmark_categorical(
            data, 
            {"A": 0.5, "B": 0.3, "C": 0.2},
            "status"
        )
        
        assert result.passed == True
    
    def test_benchmark_report(self):
        """Test complete benchmark report."""
        from misata.benchmark import BenchmarkReport, BenchmarkResult
        
        report = BenchmarkReport()
        report.add_result(BenchmarkResult("col1", "test", 0.1, 0.8, True))
        report.add_result(BenchmarkResult("col2", "test", 0.2, 0.6, True))
        report.add_result(BenchmarkResult("col3", "test", 0.9, 0.01, False))
        
        assert len(report.results) == 3
        assert report.overall_score == pytest.approx(0.667, rel=0.01)
        assert "col1" in report.summary()


class TestFeedback:
    """Tests for human-in-the-loop feedback."""
    
    def test_feedback_database_init(self):
        """Test feedback database initialization."""
        from misata.feedback import FeedbackDatabase
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_feedback.db")
            db = FeedbackDatabase(db_path)
            
            assert os.path.exists(db_path)
    
    def test_add_correction(self):
        """Test adding a correction."""
        from misata.feedback import FeedbackDatabase
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_feedback.db")
            db = FeedbackDatabase(db_path)
            
            correction_id = db.add_correction(
                table_name="users",
                column_name="email",
                original={"type": "text", "distribution_params": {"text_type": "word"}},
                corrected={"type": "text", "distribution_params": {"text_type": "email"}},
                reason="Should be email type"
            )
            
            assert correction_id > 0
    
    def test_learned_patterns(self):
        """Test that patterns are learned from corrections."""
        from misata.feedback import FeedbackDatabase
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_feedback.db")
            db = FeedbackDatabase(db_path)
            
            # Add same correction twice
            for _ in range(2):
                db.add_correction(
                    table_name="users",
                    column_name="phone",
                    original={"type": "text"},
                    corrected={"type": "text", "distribution_params": {"text_type": "phone"}},
                )
            
            patterns = db.get_learned_patterns(min_occurrences=2)
            
            assert "phone" in patterns
            assert patterns["phone"]["occurrences"] >= 2
    
    def test_feedback_loop(self):
        """Test full feedback loop."""
        from misata.feedback import HumanFeedbackLoop
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_feedback.db")
            loop = HumanFeedbackLoop(db_path)
            
            result = loop.submit_correction(
                table_name="products",
                column_name="price",
                original={"type": "int"},
                corrected={"type": "float", "distribution_params": {"min": 0}},
                reason="Prices should be positive floats"
            )
            
            assert "id" in result
            assert "message" in result


class TestAudit:
    """Tests for audit logging."""
    
    def test_audit_logger_init(self):
        """Test audit logger initialization."""
        from misata.audit import AuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            logger = AuditLogger(db_path)
            
            assert os.path.exists(db_path)
    
    def test_start_end_session(self):
        """Test session lifecycle."""
        from misata.audit import AuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            logger = AuditLogger(db_path)
            
            session_id = logger.start_session(user_id="test_user")
            assert session_id is not None
            
            logger.log("test_operation", {"key": "value"})
            logger.end_session()
            
            logs = logger.get_session_logs(session_id)
            assert len(logs) >= 2  # session_start + test_operation
    
    def test_compliance_report(self):
        """Test compliance report export."""
        from misata.audit import AuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_audit.db")
            logger = AuditLogger(db_path)
            
            logger.start_session()
            logger.log("test_op", {"data": "test"})
            logger.end_session()
            
            report = logger.export_compliance_report(format="json")
            
            assert "Misata Compliance Audit" in report
            assert "records" in report


class TestHybridLearning:
    """Tests for hybrid learning from real data."""
    
    def test_learn_numeric_column(self):
        """Test learning from numeric data."""
        from misata.hybrid import DistributionLearner
        
        learner = DistributionLearner()
        
        # Create sample data
        np.random.seed(42)
        df = pd.DataFrame({
            "age": np.random.normal(35, 10, 1000).astype(int),
            "salary": np.random.uniform(30000, 150000, 1000)
        })
        
        schema = learner.fit(df, "employees")
        
        assert "employees" in schema["columns"]
        assert len(schema["columns"]["employees"]) == 2
    
    def test_learn_categorical_column(self):
        """Test learning from categorical data."""
        from misata.hybrid import DistributionLearner
        
        learner = DistributionLearner()
        
        df = pd.DataFrame({
            "status": np.random.choice(["active", "inactive", "pending"], 1000, p=[0.6, 0.3, 0.1])
        })
        
        schema = learner.fit(df, "users")
        
        status_col = schema["columns"]["users"][0]
        assert status_col["type"] == "categorical"
        assert "choices" in status_col["distribution_params"]
    
    def test_detect_correlations(self):
        """Test correlation detection."""
        from misata.hybrid import DistributionLearner
        
        learner = DistributionLearner()
        
        # Create correlated data
        np.random.seed(42)
        x = np.random.normal(0, 1, 1000)
        y = x * 2 + np.random.normal(0, 0.1, 1000)  # Strong correlation
        
        df = pd.DataFrame({"x": x, "y": y})
        learner.fit(df, "data")
        
        assert len(learner.correlations) > 0
        assert learner.correlations[0].strength == "strong"
    
    def test_hybrid_schema_generator(self):
        """Test complete hybrid generation."""
        from misata.hybrid import HybridSchemaGenerator
        
        generator = HybridSchemaGenerator()
        
        # Learn from sample
        df = pd.DataFrame({
            "id": range(100),
            "value": np.random.normal(50, 10, 100)
        })
        
        generator.learn_from_sample({"test": df})
        
        assert generator.learned_schema is not None
        assert "test" in generator.learned_schema["columns"]
