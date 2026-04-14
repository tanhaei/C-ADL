import math
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILER_DIR = ROOT / "compiler"
sys.path.insert(0, str(COMPILER_DIR))

from cadl_parser import CADLModel, CADLParser  # noqa: E402


class TestCADLInference(unittest.TestCase):
    def setUp(self):
        self.train_ticket = CADLParser.parse(ROOT / "benchmarks" / "TrainTicket" / "model.cadl")
        self.mlops = CADLParser.parse(ROOT / "benchmarks" / "MLOps-Pipeline" / "model.cadl")

    def test_train_ticket_model_is_valid(self):
        self.assertTrue(self.train_ticket.is_valid, self.train_ticket.errors)
        self.assertGreaterEqual(len(self.train_ticket.queries), 2)

    def test_interventional_query_increases_timeout_probability(self):
        baseline = self.train_ticket.query("ui.timeout")
        intervention = self.train_ticket.run_intervention("auth.failure", True, "ui.timeout")
        self.assertGreater(intervention["probability_true"], baseline["probability_true"])
        self.assertGreater(intervention["probability_true"], 0.90)

    def test_counterfactual_reduces_training_failure(self):
        observed = self.mlops.query("training.failure")
        counterfactual = self.mlops.predict_counterfactual(
            evidence={"training.failure": True},
            intervention={"cluster_resource_contention": False},
            target="training.failure",
        )
        self.assertLess(counterfactual["probability_true"], observed["probability_true"])

    def test_expectation_query_is_marked_structural_only(self):
        iot = CADLParser.parse(ROOT / "benchmarks" / "IoT-Gateway" / "model.cadl")
        result = iot.execute_query("structural_latency_review")
        self.assertEqual(result["mode"], "structural-only")

    def test_cycle_detection_reports_w3(self):
        yaml_text = textwrap.dedent(
            """
            name: CyclicModel
            components:
              - id: a
                failure: Bernoulli(0.1)
              - id: b
                failure: Bernoulli(0.1)
            causal_links:
              - source: a.failure
                target: b.failure
                prob: 0.8
              - source: b.failure
                target: a.failure
                prob: 0.8
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "cycle.cadl"
            model_path.write_text(yaml_text, encoding="utf-8")
            model = CADLModel(model_path)
        self.assertFalse(model.is_valid)
        self.assertTrue(any(diag.rule_id == "W3" for diag in model.errors))


if __name__ == "__main__":
    unittest.main()
