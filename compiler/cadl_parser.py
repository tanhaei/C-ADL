import yaml
import argparse
import sys
import re
from pgmpy.models import BayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
import numpy as np

class CADLModel:
    def __init__(self, model_path):
        self.model_data = self._load_yaml(model_path)
        self.network = BayesianNetwork()
        self.variables = {}
        self._build_network()

    def _load_yaml(self, path):
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _parse_distribution(self, dist_str):
        """Parses strings like 'Bernoulli(0.02)' into probabilities."""
        # Simplified parser for the prototype
        if "Bernoulli" in dist_str:
            p = float(re.findall(r"[-+]?\d*\.\d+|\d+", dist_str)[0])
            # Returns [P(False), P(True)]
            return [1 - p, p]
        return [0.5, 0.5] # Default fallback

    def _build_network(self):
        print(f"Building Causal Graph for: {self.model_data['name']}...")
        
        # 1. Add Nodes (Components)
        for comp in self.model_data['components']:
            node_id = f"{comp['id']}.failure" # Simplified state model
            self.network.add_node(node_id)
            probs = self._parse_distribution(comp.get('failure_rate', 'Bernoulli(0.0)'))
            
            # Components are root nodes initially (priors)
            cpd = TabularCPD(variable=node_id, variable_card=2, values=[[probs[0]], [probs[1]]])
            self.network.add_cpds(cpd)
            self.variables[node_id] = comp

        # 2. Add Edges (Causal Links)
        # Note: In a full implementation, this handles conditional probabilities tables (CPTs)
        # Here we simulate a noisy-OR propagation logic for demonstration
        for link in self.model_data['causal_links']:
            src = link['source'] # e.g. auth.failure
            tgt = link['target'] # e.g. ui.login_latency
            
            if src not in self.network.nodes:
                self.network.add_node(src)
            if tgt not in self.network.nodes:
                self.network.add_node(tgt)
                
            self.network.add_edge(src, tgt)
            
            # Update CPD for target (Simplified logic: if parent fails, child likely fails)
            # P(Child | Parent=0), P(Child | Parent=1)
            # This overrides the initial prior if set
            cpd_tgt = TabularCPD(
                variable=tgt, 
                variable_card=2, 
                values=[[0.99, 0.1], [0.01, 0.9]], # High prob of failure if parent fails
                evidence=[src],
                evidence_card=[2]
            )
            self.network.add_cpds(cpd_tgt)

        if not self.network.check_model():
            print("Warning: Model structure checks failed (check for cycles).")

    def run_query(self, query_var, evidence=None):
        solver = VariableElimination(self.network)
        result = solver.query(variables=[query_var], evidence=evidence)
        return result

    def run_intervention(self, intervention_var, intervention_val, query_var):
        """Performs Pearl's do-calculus: do(X=x)"""
        print(f"Applying Intervention: do({intervention_var} = {intervention_val})")
        # Mutilate graph: remove incoming edges to intervention variable
        mutilated_model = self.network.copy()
        parents = list(mutilated_model.get_parents(intervention_var))
        for p in parents:
            mutilated_model.remove_edge(p, intervention_var)
            
        # Set value of intervention variable to constant
        # In pgmpy, we can simulate this by setting strong evidence on the mutilated graph
        solver = VariableElimination(mutilated_model)
        result = solver.query(variables=[query_var], evidence={intervention_var: intervention_val})
        return result

def main():
    parser = argparse.ArgumentParser(description="C-ADL Compiler & Solver")
    parser.add_argument('--model', required=True, help="Path to .yaml/.cadl model file")
    parser.add_argument('--query', help="Variable to query (e.g., ui.login_latency)")
    parser.add_argument('--do', help="Intervention in format 'var=value' (e.g., auth.failure=1)")
    
    args = parser.parse_args()
    
    cadl = CADLModel(args.model)
    
    if args.do and args.query:
        var, val = args.do.split('=')
        val = int(val)
        res = cadl.run_intervention(var, val, args.query)
        print(f"\nResult of P({args.query} | do({var}={val})):")
        print(res)
    elif args.query:
        res = cadl.run_query(args.query)
        print(f"\nResult of P({args.query}):")
        print(res)
    else:
        print("Model compiled successfully. No query provided.")

if __name__ == "__main__":
    main()
