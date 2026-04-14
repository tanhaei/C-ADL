from __future__ import annotations

from typing import Any, Dict, Iterable


class AlloyGenerator:
    """Generate an Alloy-style structural model aligned with the paper's W1-W3 checks."""

    def __init__(self, model_dict: Dict[str, Any]):
        self.data = model_dict
        self.buffer = []

    def generate(self) -> str:
        self._write_header()
        self._write_signatures()
        self._write_links()
        self._write_well_formed_predicate()
        return "\n".join(self.buffer) + "\n"

    def _write_header(self) -> None:
        self.buffer.extend(
            [
                "module cadl_model",
                "",
                "abstract sig Var { parent: set Var }",
                "sig Endogenous extends Var {}",
                "sig Exogenous extends Var {}",
                "sig CausalLink { source: one Var, target: one Var }",
                "",
            ]
        )

    def _write_signatures(self) -> None:
        for name, spec in self.data.get("variables", {}).items():
            clean = self._clean(name)
            kind = "Exogenous" if spec.get("exogenous") else "Endogenous"
            self.buffer.append(f"one sig {clean} extends {kind} {{}}")
        self.buffer.append("")

    def _write_links(self) -> None:
        for idx, link in enumerate(self.data.get("links", [])):
            src = self._clean(link["source"])
            tgt = self._clean(link["target"])
            self.buffer.append(f"one sig L{idx} extends CausalLink {{}} {{")
            self.buffer.append(f"  source = {src}")
            self.buffer.append(f"  target = {tgt}")
            self.buffer.append("}")
        self.buffer.append("")
        self.buffer.append("fact ParentProjection {")
        self.buffer.append("  all l: CausalLink | l.target in l.source.parent")
        self.buffer.append("}")
        self.buffer.append("")

    def _write_well_formed_predicate(self) -> None:
        self.buffer.extend(
            [
                "pred wellFormedModel {",
                "  // W1: reference integrity",
                "  all l: CausalLink | some l.source and some l.target",
                "  // W3: acyclic causal graph",
                "  no v: Var | v in v.^parent",
                "}",
                "",
                "run wellFormedModel for 20",
            ]
        )

    @staticmethod
    def _clean(name: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in name)
