from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import networkx as nx
import yaml


RESERVED_COMPONENT_KEYS = {
    "id",
    "type",
    "description",
    "version",
    "kind",
    "metadata",
    "tags",
    "owner",
}


@dataclass
class Diagnostic:
    severity: str
    rule_id: str
    message: str
    location: str
    hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "message": self.message,
            "location": self.location,
        }
        if self.hint:
            data["hint"] = self.hint
        return data


@dataclass
class VariableSpec:
    name: str
    component: Optional[str]
    property_name: str
    declared_value: Any
    domain: str
    unit: Optional[str]
    discrete: bool
    fully_parameterized: bool
    exogenous: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class LinkSpec:
    source: str
    target: str
    prob: Optional[float] = None
    do_expression: Optional[str] = None
    functional_form: Optional[str] = None
    description: Optional[str] = None
    location: str = "causal_links"


@dataclass
class QuerySpec:
    query_id: str
    raw_query: str
    kind: str
    target: str
    intervention: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    evidence_ops: Dict[str, str] = field(default_factory=dict)
    structural_only_reasons: List[str] = field(default_factory=list)
    location: str = "counterfactuals"

    @property
    def exact_ready(self) -> bool:
        return not self.structural_only_reasons


class CADLValidationError(Exception):
    def __init__(self, diagnostics: Iterable[Diagnostic]):
        self.diagnostics = list(diagnostics)
        super().__init__("Model validation failed")


class CausalInferenceEngine:
    """Discrete Bernoulli backend implementing observational, interventional, and evidence-aware counterfactual queries."""

    def __init__(self, variables: Dict[str, VariableSpec], links: List[LinkSpec]):
        self.variables = variables
        self.links = links
        self.graph = nx.DiGraph()
        self.supported_nodes: Dict[str, VariableSpec] = {}
        self.link_index: Dict[Tuple[str, str], LinkSpec] = {}
        self.parents: Dict[str, List[str]] = {}
        self.cpds: Dict[str, Dict[Tuple[int, ...], float]] = {}
        self.order: List[str] = []
        self._build_model()

    def _build_model(self) -> None:
        supported = {
            name: spec
            for name, spec in self.variables.items()
            if spec.discrete and spec.fully_parameterized
        }
        for node in supported:
            self.graph.add_node(node)
        for link in self.links:
            if link.source in supported and link.target in supported:
                self.link_index[(link.source, link.target)] = link
                self.graph.add_edge(link.source, link.target)
        self.supported_nodes = supported
        self.order = list(nx.topological_sort(self.graph))

        for node in self.order:
            parents = sorted(self.graph.predecessors(node))
            self.parents[node] = parents
            prior = prior_true_prob(supported[node])
            if not parents:
                if prior is None:
                    raise ValueError(f"Missing prior for root variable: {node}")
                self.cpds[node] = {(): prior}
                continue

            base_prob = 0.0 if prior is None else prior
            table: Dict[Tuple[int, ...], float] = {}
            for assignment in itertools.product([0, 1], repeat=len(parents)):
                p_true = base_prob
                for parent, parent_value in zip(parents, assignment):
                    if parent_value:
                        influence = link_true_effect(self.link_index[(parent, node)])
                        p_true = 1.0 - (1.0 - p_true) * (1.0 - influence)
                table[assignment] = min(max(p_true, 0.0), 1.0)
            self.cpds[node] = table

    def is_supported(self, variable: str) -> bool:
        return variable in self.supported_nodes

    def query_probability(
        self,
        target: str,
        evidence: Optional[Dict[str, int]] = None,
        intervention: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        parents, cpds, order = self._mutilated_model(intervention or {})
        false_prob, true_prob = self._distribution(target, evidence or {}, parents, cpds, order)
        return probability_result(target, false_prob, true_prob, mode="probability")

    def predict_counterfactual(
        self,
        target: str,
        evidence: Dict[str, int],
        intervention: Dict[str, int],
    ) -> Dict[str, Any]:
        roots = [node for node in self.order if not self.parents[node]]
        posterior_roots = self._joint_distribution(roots, evidence, self.parents, self.cpds, self.order)
        parents, cpds, order = self._mutilated_model(intervention)

        aggregate_false = 0.0
        aggregate_true = 0.0
        for values, weight in posterior_roots.items():
            if weight <= 0:
                continue
            root_assignment = {node: value for node, value in zip(roots, values) if node not in intervention}
            false_prob, true_prob = self._distribution(target, root_assignment, parents, cpds, order)
            aggregate_false += weight * false_prob
            aggregate_true += weight * true_prob

        total = aggregate_false + aggregate_true
        if total == 0:
            raise ValueError("Posterior mass vanished during counterfactual evaluation.")
        aggregate_false /= total
        aggregate_true /= total
        result = probability_result(target, aggregate_false, aggregate_true, mode="counterfactual")
        result["roots_conditioned"] = roots
        return result

    def _distribution(
        self,
        target: str,
        evidence: Dict[str, int],
        parents: Dict[str, List[str]],
        cpds: Dict[str, Dict[Tuple[int, ...], float]],
        order: List[str],
    ) -> Tuple[float, float]:
        if target in evidence:
            target_value = evidence[target]
            return (1.0, 0.0) if target_value == 0 else (0.0, 1.0)

        false_prob = self._probability_with_assignment(
            {**evidence, target: 0}, parents, cpds, order
        )
        true_prob = self._probability_with_assignment(
            {**evidence, target: 1}, parents, cpds, order
        )
        total = false_prob + true_prob
        if total == 0:
            raise ValueError(f"Zero posterior mass for target '{target}'.")
        return false_prob / total, true_prob / total

    def _joint_distribution(
        self,
        query_nodes: List[str],
        evidence: Dict[str, int],
        parents: Dict[str, List[str]],
        cpds: Dict[str, Dict[Tuple[int, ...], float]],
        order: List[str],
    ) -> Dict[Tuple[int, ...], float]:
        distribution: Dict[Tuple[int, ...], float] = {}
        for values in itertools.product([0, 1], repeat=len(query_nodes)):
            assignment = {**evidence, **dict(zip(query_nodes, values))}
            distribution[values] = self._probability_with_assignment(assignment, parents, cpds, order)
        total = sum(distribution.values())
        if total == 0:
            raise ValueError("Zero probability mass while conditioning on evidence.")
        return {values: prob / total for values, prob in distribution.items()}

    def _probability_with_assignment(
        self,
        partial_assignment: Dict[str, int],
        parents: Dict[str, List[str]],
        cpds: Dict[str, Dict[Tuple[int, ...], float]],
        order: List[str],
    ) -> float:
        hidden = [node for node in order if node not in partial_assignment]
        total = 0.0
        for values in itertools.product([0, 1], repeat=len(hidden)):
            full_assignment = dict(partial_assignment)
            full_assignment.update(dict(zip(hidden, values)))
            total += self._joint_probability(full_assignment, parents, cpds, order)
        return total

    def _joint_probability(
        self,
        assignment: Dict[str, int],
        parents: Dict[str, List[str]],
        cpds: Dict[str, Dict[Tuple[int, ...], float]],
        order: List[str],
    ) -> float:
        probability = 1.0
        for node in order:
            parent_values = tuple(assignment[parent] for parent in parents[node])
            p_true = cpds[node][parent_values]
            probability *= p_true if assignment[node] else (1.0 - p_true)
        return probability

    def _mutilated_model(
        self, intervention: Dict[str, int]
    ) -> Tuple[Dict[str, List[str]], Dict[str, Dict[Tuple[int, ...], float]], List[str]]:
        parents = {node: list(node_parents) for node, node_parents in self.parents.items()}
        cpds = {
            node: {key: value for key, value in table.items()}
            for node, table in self.cpds.items()
        }
        for variable, value in intervention.items():
            if variable not in parents:
                continue
            parents[variable] = []
            cpds[variable] = {(): float(value)}
        return parents, cpds, list(self.order)


class CADLModel:
    def __init__(self, model_path: str | Path):
        self.path = Path(model_path)
        self.raw = self._load_yaml(self.path)
        self.name = self.raw.get("name", self.path.stem)
        self.variables: Dict[str, VariableSpec] = {}
        self.links: List[LinkSpec] = []
        self.queries: List[QuerySpec] = []
        self.diagnostics: List[Diagnostic] = []
        self.graph = nx.DiGraph()
        self._parse_components()
        self._parse_exogenous()
        self._parse_links()
        self._parse_queries()
        self._validate()
        self.inference_engine: Optional[CausalInferenceEngine] = None
        if self._can_build_discrete_backend():
            self.inference_engine = CausalInferenceEngine(self.variables, self.links)

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("Top-level C-ADL document must be a YAML mapping.")
        return data

    def _parse_components(self) -> None:
        for idx, component in enumerate(self.raw.get("components", [])):
            component_id = component.get("id")
            if not component_id:
                self._error("W1", "Component is missing an id.", f"components[{idx}]", "Add an 'id' field.")
                continue
            for key, value in component.items():
                if key in RESERVED_COMPONENT_KEYS:
                    continue
                name = f"{component_id}.{key}"
                spec = classify_value(name, value, exogenous=False, component=component_id, property_name=key)
                self.variables[name] = spec
                self.graph.add_node(name)

    def _parse_exogenous(self) -> None:
        for idx, entry in enumerate(self.raw.get("exogenous", [])):
            if isinstance(entry, dict) and "id" in entry:
                exo_id = entry["id"]
                value = entry.get("distribution", entry.get("type", entry.get("value", "Boolean")))
            elif isinstance(entry, dict) and len(entry) == 1:
                exo_id, value = next(iter(entry.items()))
            else:
                self._error(
                    "W1",
                    "Exogenous declaration must be either {id, distribution} or {name: distribution}.",
                    f"exogenous[{idx}]",
                    "Use 'id' plus 'distribution' for readability.",
                )
                continue
            spec = classify_value(exo_id, value, exogenous=True, component=None, property_name=exo_id)
            self.variables[exo_id] = spec
            self.graph.add_node(exo_id)

    def _parse_links(self) -> None:
        for idx, link in enumerate(self.raw.get("causal_links", [])):
            source = link.get("source")
            target = link.get("target")
            location = f"causal_links[{idx}]"
            if not source or not target:
                self._error("W1", "Causal link must define both source and target.", location)
                continue
            prob = link.get("prob")
            if prob is not None:
                try:
                    prob = float(prob)
                except (TypeError, ValueError):
                    self._error("W2", f"Invalid prob value: {prob}", location, "Use a numeric value between 0 and 1.")
                    prob = None
            spec = LinkSpec(
                source=source,
                target=target,
                prob=prob,
                do_expression=link.get("do"),
                functional_form=link.get("functional_form"),
                description=link.get("description"),
                location=location,
            )
            self.links.append(spec)
            self.graph.add_edge(source, target)

    def _parse_queries(self) -> None:
        for idx, item in enumerate(self.raw.get("counterfactuals", [])):
            location = f"counterfactuals[{idx}]"
            query_text = item.get("query")
            if not query_text:
                self._error("W1", "Query entry is missing a 'query' field.", location)
                continue
            try:
                parsed = parse_query_text(query_text)
            except ValueError as exc:
                self._error("W1", str(exc), location, "Use P(...) or E(...) query syntax.")
                continue
            intervention = dict(parsed["intervention"])
            external_intervention = item.get("intervention")
            if external_intervention:
                intervention.update(parse_do_expression(external_intervention, allow_targetless=True))
            query = QuerySpec(
                query_id=item.get("id", f"query_{idx + 1}"),
                raw_query=query_text,
                kind=parsed["kind"],
                target=parsed["target"],
                intervention=intervention,
                evidence=parsed["evidence"],
                evidence_ops=parsed["evidence_ops"],
                location=location,
            )
            self.queries.append(query)

    def _validate(self) -> None:
        self._validate_reference_integrity()
        self._validate_type_compatibility()
        self._validate_dag()
        self._validate_query_adequacy()

    def _validate_reference_integrity(self) -> None:
        declared = set(self.variables)
        for link in self.links:
            if link.source not in declared:
                self._error("W1", f"Undefined source variable: {link.source}", link.location, f"Declare '{link.source}' first.")
            if link.target not in declared:
                self._error("W1", f"Undefined target variable: {link.target}", link.location, f"Declare '{link.target}' first.")
            if link.do_expression:
                try:
                    parsed = parse_link_do_expression(link.do_expression)
                except ValueError as exc:
                    self._error("W2", str(exc), link.location, "Use 'do(x=true) -> y=value'.")
                    continue
                if parsed["intervention_var"] != link.source:
                    self._error(
                        "W2",
                        f"do-expression must intervene on the source variable '{link.source}', got '{parsed['intervention_var']}'.",
                        link.location,
                    )
                if parsed["target_var"] != link.target:
                    self._error(
                        "W2",
                        f"do-expression must assign the link target '{link.target}', got '{parsed['target_var']}'.",
                        link.location,
                    )
        for query in self.queries:
            if query.target not in declared:
                self._error("W1", f"Undefined query target: {query.target}", query.location)
            for variable in query.intervention:
                if variable not in declared:
                    self._error("W1", f"Undefined intervention variable: {variable}", query.location)
            for variable in query.evidence:
                if variable not in declared:
                    self._error("W1", f"Undefined evidence variable: {variable}", query.location)

    def _validate_type_compatibility(self) -> None:
        for link in self.links:
            source = self.variables.get(link.source)
            target = self.variables.get(link.target)
            if not source or not target:
                continue
            if link.prob is not None and not target.discrete:
                self._error(
                    "W2",
                    f"prob specification requires a discrete/Boolean target, but '{target.name}' is '{target.domain}'.",
                    link.location,
                    "Use a structural equation or do-expression for continuous targets.",
                )
            if link.prob is not None and not (0.0 <= link.prob <= 1.0):
                self._error("W2", f"Probability must be in [0, 1], got {link.prob}.", link.location)
            if link.functional_form and target.discrete and not re.search(r"=|>|<", link.functional_form):
                self._warning(
                    "W2",
                    f"Could not infer codomain of functional form for '{target.name}'.",
                    link.location,
                    "Add an explicit Boolean assignment or use prob for Bernoulli targets.",
                )

    def _validate_dag(self) -> None:
        graph = nx.DiGraph()
        for link in self.links:
            if link.source in self.variables and link.target in self.variables:
                graph.add_edge(link.source, link.target)
        try:
            cycle = nx.find_cycle(graph, orientation="original")
        except nx.NetworkXNoCycle:
            return
        path_nodes = [edge[0] for edge in cycle] + [cycle[0][0]]
        witness = " -> ".join(path_nodes)
        self._error(
            "W3",
            f"Causal graph must be acyclic. Minimal witness cycle: {witness}",
            "causal_links",
            "Remove or redirect one edge in the cycle.",
        )

    def _validate_query_adequacy(self) -> None:
        exact_nodes = set()
        if self._can_build_discrete_backend():
            exact_nodes = {
                name
                for name, spec in self.variables.items()
                if spec.discrete and spec.fully_parameterized
            }
        for query in self.queries:
            target_spec = self.variables.get(query.target)
            if not target_spec:
                query.structural_only_reasons.append("Undefined target variable.")
                continue
            if query.kind == "P":
                if not target_spec.discrete:
                    query.structural_only_reasons.append(
                        f"Probability query target '{query.target}' is not discrete."
                    )
                if query.target not in exact_nodes:
                    query.structural_only_reasons.append(
                        f"Target '{query.target}' is not fully parameterized for exact discrete inference."
                    )
            elif query.kind == "E":
                query.structural_only_reasons.append(
                    "Expectation queries are preserved structurally; exact continuous inference is not implemented in the current backend."
                )
            for variable, op in query.evidence_ops.items():
                spec = self.variables.get(variable)
                if not spec:
                    continue
                if op != "=":
                    query.structural_only_reasons.append(
                        f"Evidence '{variable} {op} ...' requires symbolic handling."
                    )
                elif variable not in exact_nodes:
                    query.structural_only_reasons.append(
                        f"Evidence variable '{variable}' is not fully parameterized for exact inference."
                    )
            for variable in query.intervention:
                spec = self.variables.get(variable)
                if not spec:
                    continue
                if not spec.discrete:
                    query.structural_only_reasons.append(
                        f"Intervention on '{variable}' is structural-only because the variable is not discrete."
                    )
                elif variable not in exact_nodes:
                    query.structural_only_reasons.append(
                        f"Intervention variable '{variable}' is not fully parameterized for exact inference."
                    )

    def _can_build_discrete_backend(self) -> bool:
        if any(diag.severity == "error" for diag in self.diagnostics if diag.rule_id in {"W1", "W2", "W3"}):
            return False
        supported_nodes = [
            spec for spec in self.variables.values() if spec.discrete and spec.fully_parameterized
        ]
        return bool(supported_nodes)

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise CADLValidationError(self.errors)

    def query(self, target: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.require_valid()
        if not self.variables.get(target):
            raise ValueError(f"Unknown variable: {target}")
        if not self.inference_engine or not self.inference_engine.is_supported(target):
            return {
                "mode": "structural-only",
                "target": target,
                "reason": "Target is not compiled into the discrete backend.",
            }
        encoded_evidence = encode_evidence(evidence or {}, self.variables)
        return self.inference_engine.query_probability(target, evidence=encoded_evidence)

    def run_intervention(
        self,
        intervention_var: str,
        intervention_value: Any,
        query_var: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.require_valid()
        if not self.inference_engine:
            return {
                "mode": "structural-only",
                "target": query_var,
                "reason": "Discrete intervention backend is unavailable for this model.",
            }
        if not self.inference_engine.is_supported(query_var):
            return {
                "mode": "structural-only",
                "target": query_var,
                "reason": f"Query target '{query_var}' is not compiled into the discrete backend.",
            }
        encoded_intervention = encode_evidence({intervention_var: intervention_value}, self.variables)
        encoded_evidence = encode_evidence(evidence or {}, self.variables)
        result = self.inference_engine.query_probability(
            query_var,
            evidence=encoded_evidence,
            intervention=encoded_intervention,
        )
        result["intervention"] = {intervention_var: encoded_intervention[intervention_var]}
        return result

    def predict_counterfactual(
        self,
        evidence: Dict[str, Any],
        intervention: Dict[str, Any],
        target: str,
    ) -> Dict[str, Any]:
        self.require_valid()
        if not self.inference_engine or not self.inference_engine.is_supported(target):
            return {
                "mode": "structural-only",
                "target": target,
                "reason": f"Counterfactual target '{target}' is not compiled into the discrete backend.",
            }
        encoded_evidence = encode_evidence(evidence, self.variables)
        encoded_intervention = encode_evidence(intervention, self.variables)
        result = self.inference_engine.predict_counterfactual(target, encoded_evidence, encoded_intervention)
        result["evidence"] = encoded_evidence
        result["intervention"] = encoded_intervention
        return result

    def execute_query(self, query_id: str) -> Dict[str, Any]:
        query = next((item for item in self.queries if item.query_id == query_id), None)
        if not query:
            raise ValueError(f"Unknown query id: {query_id}")
        if query.structural_only_reasons:
            return {
                "mode": "structural-only",
                "query_id": query.query_id,
                "target": query.target,
                "reasons": query.structural_only_reasons,
            }
        if query.intervention and query.evidence:
            return self.predict_counterfactual(query.evidence, query.intervention, query.target)
        if query.intervention:
            intervention_var, intervention_value = next(iter(query.intervention.items()))
            return self.run_intervention(intervention_var, intervention_value, query.target)
        return self.query(query.target, evidence=query.evidence)

    def to_ir(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "variables": {
                name: {
                    "component": spec.component,
                    "property": spec.property_name,
                    "domain": spec.domain,
                    "unit": spec.unit,
                    "discrete": spec.discrete,
                    "fully_parameterized": spec.fully_parameterized,
                    "exogenous": spec.exogenous,
                }
                for name, spec in sorted(self.variables.items())
            },
            "links": [
                {
                    "source": link.source,
                    "target": link.target,
                    "prob": link.prob,
                    "do": link.do_expression,
                    "functional_form": link.functional_form,
                }
                for link in self.links
            ],
            "queries": [
                {
                    "id": query.query_id,
                    "kind": query.kind,
                    "target": query.target,
                    "intervention": query.intervention,
                    "evidence": query.evidence,
                    "structural_only_reasons": query.structural_only_reasons,
                }
                for query in self.queries
            ],
            "diagnostics": [diag.to_dict() for diag in self.diagnostics],
        }

    def export_mermaid(self) -> str:
        lines = ["flowchart LR"]
        for name, spec in sorted(self.variables.items()):
            node_id = safe_node_id(name)
            label = name
            shape_open = "([" if spec.exogenous else "["
            shape_close = "])" if spec.exogenous else "]"
            lines.append(f"    {node_id}{shape_open}{label}{shape_close}")
        for link in self.links:
            if link.source in self.variables and link.target in self.variables:
                src = safe_node_id(link.source)
                tgt = safe_node_id(link.target)
                annotation = []
                if link.prob is not None:
                    annotation.append(f"prob={link.prob}")
                if link.do_expression:
                    annotation.append("do")
                edge_label = " |" + ", ".join(annotation) + "|" if annotation else ""
                lines.append(f"    {src} -->{edge_label} {tgt}")
        return "\n".join(lines) + "\n"

    def export_report_manifest(self) -> Dict[str, Any]:
        return {
            "model": self.name,
            "path": str(self.path),
            "validation": {
                "passed": self.is_valid,
                "errors": [diag.to_dict() for diag in self.errors],
                "warnings": [diag.to_dict() for diag in self.warnings],
            },
            "query_table": [
                {
                    "id": query.query_id,
                    "raw": query.raw_query,
                    "kind": query.kind,
                    "target": query.target,
                    "intervention": query.intervention,
                    "evidence": query.evidence,
                    "mode": "exact" if query.exact_ready else "structural-only",
                }
                for query in self.queries
            ],
        }

    def _error(self, rule_id: str, message: str, location: str, hint: Optional[str] = None) -> None:
        self.diagnostics.append(Diagnostic("error", rule_id, message, location, hint))

    def _warning(self, rule_id: str, message: str, location: str, hint: Optional[str] = None) -> None:
        self.diagnostics.append(Diagnostic("warning", rule_id, message, location, hint))


class CADLParser:
    @staticmethod
    def parse(model_path: str | Path) -> CADLModel:
        return CADLModel(model_path)


def classify_value(
    name: str,
    raw_value: Any,
    exogenous: bool,
    component: Optional[str],
    property_name: str,
) -> VariableSpec:
    text = str(raw_value).strip() if raw_value is not None else ""
    unit = None
    discrete = False
    fully_parameterized = False
    domain = "Unknown"
    notes: List[str] = []

    if matches_distribution(text, "Bernoulli"):
        discrete = True
        fully_parameterized = bernoulli_parameter(text) is not None
        domain = "Boolean"
    elif text == "Boolean":
        discrete = True
        fully_parameterized = False
        domain = "Boolean"
    elif matches_distribution(text, "Categorical"):
        discrete = True
        fully_parameterized = True
        domain = "Categorical"
    elif re.match(r"^(Real|Integer)\b", text):
        discrete = False
        fully_parameterized = False
        domain, unit = parse_declared_type(text)
    elif any(matches_distribution(text, family) for family in ["Normal", "Exponential", "Uniform", "LogNormal"]):
        discrete = False
        fully_parameterized = True
        domain = distribution_family(text)
        unit = trailing_unit(text)
        if "~Uniform" in text:
            notes.append("range_or_prior")
    elif isinstance(raw_value, (int, float)):
        discrete = False
        fully_parameterized = True
        domain = "Constant"
    else:
        domain = "Opaque"
        fully_parameterized = False
        notes.append("unclassified")

    return VariableSpec(
        name=name,
        component=component,
        property_name=property_name,
        declared_value=raw_value,
        domain=domain,
        unit=unit,
        discrete=discrete,
        fully_parameterized=fully_parameterized,
        exogenous=exogenous,
        notes=notes,
    )


def parse_declared_type(text: str) -> Tuple[str, Optional[str]]:
    match = re.match(r"^(Real|Integer)\s*(.*)$", text)
    if not match:
        return text, None
    domain = match.group(1)
    unit = match.group(2).strip() or None
    return domain, unit


def trailing_unit(text: str) -> Optional[str]:
    match = re.match(r"^[A-Za-z]+\([^)]*\)\s*(.*)$", text)
    if not match:
        return None
    unit = match.group(1).strip()
    return unit or None


def distribution_family(text: str) -> str:
    match = re.match(r"^([A-Za-z]+)\(", text)
    return match.group(1) if match else "Distribution"


def matches_distribution(text: str, family: str) -> bool:
    return bool(re.match(rf"^{family}\(", text))


def bernoulli_parameter(text: str) -> Optional[float]:
    if not matches_distribution(text, "Bernoulli"):
        return None
    match = re.search(r"Bernoulli\(([^)]+)\)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def prior_true_prob(spec: VariableSpec) -> Optional[float]:
    if not spec.discrete:
        return None
    value = spec.declared_value
    if isinstance(value, str):
        return bernoulli_parameter(value)
    return None


def link_true_effect(link: LinkSpec) -> float:
    if link.prob is not None:
        return link.prob
    if link.do_expression:
        parsed = parse_link_do_expression(link.do_expression)
        intervention_value = normalize_scalar(parsed["intervention_value"])
        target_value = normalize_scalar(parsed["target_value"])
        if intervention_value in {0, 1} and target_value in {0, 1} and intervention_value == 1:
            return float(target_value)
    return 1.0


def probability_result(target: str, false_prob: float, true_prob: float, mode: str) -> Dict[str, Any]:
    return {
        "mode": mode,
        "target": target,
        "distribution": {"false": false_prob, "true": true_prob},
        "probability_true": true_prob,
        "probability_false": false_prob,
    }


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return 1
        if lowered in {"false", "0", "no"}:
            return 0
        try:
            if "." in lowered:
                return float(lowered)
            return int(lowered)
        except ValueError:
            return value.strip()
    return value


def encode_evidence(evidence: Dict[str, Any], variables: Dict[str, VariableSpec]) -> Dict[str, int]:
    encoded: Dict[str, int] = {}
    for variable, value in evidence.items():
        spec = variables.get(variable)
        if not spec:
            raise ValueError(f"Unknown variable in evidence/intervention: {variable}")
        normalized = normalize_scalar(value)
        if spec.discrete:
            if normalized not in {0, 1}:
                raise ValueError(f"Boolean variable '{variable}' expects true/false or 0/1, got {value!r}")
            encoded[variable] = int(normalized)
        else:
            raise ValueError(f"Continuous evidence is not supported by the exact discrete backend: {variable}")
    return encoded


def split_conditions(text: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
            continue
        current.append(char)
    final = "".join(current).strip()
    if final:
        parts.append(final)
    return parts


def parse_query_text(query_text: str) -> Dict[str, Any]:
    match = re.match(r"^\s*([PE])\((.*)\)\s*$", query_text)
    if not match:
        raise ValueError(f"Unsupported query syntax: {query_text}")
    kind = match.group(1)
    inner = match.group(2).strip()
    if "|" in inner:
        target_text, conditions_text = [part.strip() for part in inner.split("|", 1)]
    else:
        target_text, conditions_text = inner, ""
    target = parse_target_expression(target_text)
    intervention: Dict[str, Any] = {}
    evidence: Dict[str, Any] = {}
    evidence_ops: Dict[str, str] = {}
    if conditions_text:
        for condition in split_conditions(conditions_text):
            if condition.startswith("do("):
                intervention.update(parse_do_expression(condition, allow_targetless=True))
            else:
                variable, op, value = parse_condition(condition)
                evidence[variable] = value
                evidence_ops[variable] = op
    return {
        "kind": kind,
        "target": target,
        "intervention": intervention,
        "evidence": evidence,
        "evidence_ops": evidence_ops,
    }


def parse_target_expression(text: str) -> str:
    variable, _op, _value = parse_condition(text, allow_plain=True)
    return variable


def parse_condition(text: str, allow_plain: bool = False) -> Tuple[str, str, Any]:
    pattern = r"^([A-Za-z_][A-Za-z0-9_.]*)\s*(<=|>=|==|=|<|>)?\s*(.*)$"
    match = re.match(pattern, text.strip())
    if not match:
        raise ValueError(f"Invalid condition: {text}")
    variable = match.group(1)
    op = match.group(2) or ""
    rhs = match.group(3).strip()
    if allow_plain and not op:
        return variable, "", None
    if not op:
        raise ValueError(f"Condition is missing an operator: {text}")
    return variable, "=" if op == "==" else op, normalize_scalar(rhs)


def parse_do_expression(text: str, allow_targetless: bool = False) -> Dict[str, Any]:
    text = text.strip()
    match = re.match(r"^do\(([^=]+)=([^\)]+)\)$", text)
    if match:
        return {match.group(1).strip(): normalize_scalar(match.group(2).strip())}
    if allow_targetless:
        match = re.match(r"^do\(([^=]+)=([^\)]+)\)\s*$", text)
        if match:
            return {match.group(1).strip(): normalize_scalar(match.group(2).strip())}
    raise ValueError(f"Invalid intervention syntax: {text}")


def parse_link_do_expression(text: str) -> Dict[str, Any]:
    match = re.match(r"^do\(([^=]+)=([^\)]+)\)\s*->\s*([^=]+)=\s*(.+)$", text.strip())
    if not match:
        raise ValueError(f"Invalid link do-expression: {text}")
    return {
        "intervention_var": match.group(1).strip(),
        "intervention_value": match.group(2).strip(),
        "target_var": match.group(3).strip(),
        "target_value": match.group(4).strip(),
    }


def safe_node_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=False)


def cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="C-ADL compiler, validator, and discrete causal solver")
    parser.add_argument("command", choices=["check", "ir", "query", "intervene", "counterfactual", "mermaid", "report"])
    parser.add_argument("--model", required=True, help="Path to a .cadl/.yaml model")
    parser.add_argument("--target", help="Query target variable")
    parser.add_argument("--query-id", help="Named query from counterfactuals[]")
    parser.add_argument("--do", dest="do_expr", help="Intervention in the form var=value")
    parser.add_argument("--evidence", help="Comma-separated evidence, e.g. a=true,b=false")
    args = parser.parse_args(argv)

    model = CADLModel(args.model)

    if args.command == "check":
        payload = {
            "model": model.name,
            "valid": model.is_valid,
            "errors": [diag.to_dict() for diag in model.errors],
            "warnings": [diag.to_dict() for diag in model.warnings],
        }
        print(pretty_json(payload))
        return 0 if model.is_valid else 1

    if args.command == "ir":
        print(pretty_json(model.to_ir()))
        return 0

    if args.command == "mermaid":
        print(model.export_mermaid())
        return 0

    if args.command == "report":
        print(pretty_json(model.export_report_manifest()))
        return 0

    if args.query_id:
        print(pretty_json(model.execute_query(args.query_id)))
        return 0

    evidence = parse_cli_assignments(args.evidence) if args.evidence else {}

    if args.command == "query":
        if not args.target:
            raise SystemExit("--target is required for query")
        print(pretty_json(model.query(args.target, evidence=evidence)))
        return 0

    if args.command == "intervene":
        if not args.target or not args.do_expr:
            raise SystemExit("--target and --do are required for intervene")
        intervention = parse_cli_assignments(args.do_expr)
        if len(intervention) != 1:
            raise SystemExit("--do accepts exactly one assignment")
        variable, value = next(iter(intervention.items()))
        print(pretty_json(model.run_intervention(variable, value, args.target, evidence=evidence)))
        return 0

    if args.command == "counterfactual":
        if not args.target or not args.do_expr:
            raise SystemExit("--target and --do are required for counterfactual")
        intervention = parse_cli_assignments(args.do_expr)
        print(pretty_json(model.predict_counterfactual(evidence=evidence, intervention=intervention, target=args.target)))
        return 0

    return 0


def parse_cli_assignments(text: str) -> Dict[str, Any]:
    assignments: Dict[str, Any] = {}
    for piece in split_conditions(text):
        variable, _op, value = parse_condition(piece)
        assignments[variable] = value
    return assignments


if __name__ == "__main__":
    sys.exit(cli())
