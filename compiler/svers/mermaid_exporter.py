from __future__ import annotations

from typing import Any, Dict


def export_mermaid(ir: Dict[str, Any]) -> str:
    lines = ["flowchart LR"]
    for name, spec in sorted(ir.get("variables", {}).items()):
        node_id = "".join(ch if ch.isalnum() else "_" for ch in name)
        if spec.get("exogenous"):
            lines.append(f"    {node_id}([{name}])")
        else:
            lines.append(f"    {node_id}[{name}]")
    for link in ir.get("links", []):
        src = "".join(ch if ch.isalnum() else "_" for ch in link["source"])
        tgt = "".join(ch if ch.isalnum() else "_" for ch in link["target"])
        label = []
        if link.get("prob") is not None:
            label.append(f"prob={link['prob']}")
        if link.get("do"):
            label.append("do")
        edge = f" |{', '.join(label)}|" if label else ""
        lines.append(f"    {src} -->{edge} {tgt}")
    return "\n".join(lines) + "\n"
