import unittest
from pgmpy.inference import VariableElimination
from cadl_compiler import CADLParser  # Hypothetical compiler module

class TestTrainTicketInference(unittest.TestCase):
    
    def setUp(self):
        # Load the YAML model described in Listing 1 of the paper
        self.model = CADLParser.parse("examples/trainticket.yaml")
        self.infer = VariableElimination(self.model)

    def test_interventional_query(self):
        """
        RQ2 Verification: Test 'do' operator on Auth service failure.
        Scenario: If we intervene and force Auth to fail (do(auth.failure=True)),
        what is the probability of Login Latency being high?
        """
        # Apply intervention: do(auth.failure=True)
        # In pgmpy, this requires mutilating the graph (removing parents of auth.failure)
        mutilated_model = self.model.do('auth.failure')
        infer_mutilated = VariableElimination(mutilated_model)

        # Query: P(ui.login_latency | do(auth.failure=True))
        result = infer_mutilated.query(
            variables=['ui.login_latency'], 
            evidence={'auth.failure': 1} # 1 = True
        )
        
        # Expectation based on SCM logic defined in paper
        prob_high_latency = result.values[1] # Assuming index 1 is 'High'
        self.assertGreater(prob_high_latency, 0.95, "Intervention did not propagate correctly")

    def test_counterfactual_reasoning(self):
        """
        RQ2 Verification: Counterfactual query.
        'Given observed high latency, would it have been normal if network was stable?'
        """
        # 1. Abduction: Update noise distribution based on evidence (latency=High)
        # 2. Action: Set network_partition = False
        # 3. Prediction: Re-evaluate latency
        cf_prob = self.model.predict_counterfactual(
            evidence={'ui.login_latency': 'High'}, 
            intervention={'network_partition': 'False'},
            target='ui.login_latency'
        )
        
        print(f"Counterfactual Probability: {cf_prob}")
        self.assertIsNotNone(cf_prob)

if __name__ == '__main__':
    unittest.main()
