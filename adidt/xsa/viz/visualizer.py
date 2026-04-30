# adidt/xsa/visualizer.py
"""Generate an interactive HTML report visualising XSA topology and DTS output."""

import html
import json
import re
from pathlib import Path
from typing import Any

from ..parse.topology import XsaTopology

_D3_BUNDLE_PATH = Path(__file__).parent / "d3_bundle.js"
_D3_BUNDLE = _D3_BUNDLE_PATH.read_text() if _D3_BUNDLE_PATH.exists() else ""


class HtmlVisualizer:
    """Generates a self-contained interactive HTML report."""

    def generate(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        merged_dts: str,
        output_dir: Path,
        name: str,
    ) -> str:
        """Render and write a self-contained HTML report; returns the HTML string."""
        if not _D3_BUNDLE:
            raise RuntimeError(
                "D3 bundle missing — run scripts/embed_d3.py to generate "
                "adidt/xsa/d3_bundle.js"
            )
        tree_data = self._dts_to_tree(merged_dts)
        clock_data = self._build_clock_data(topology, cfg)
        jesd_data = self._build_jesd_data(topology)
        wiring_data = self._build_wiring_data(topology, cfg, merged_dts)
        coverage_data = self._build_match_coverage(topology, merged_dts)
        html_content = self._render_html(
            tree_data, clock_data, jesd_data, wiring_data, coverage_data, name
        )
        safe_name = re.sub(r"[^\w\-.]", "_", name)
        (output_dir / f"{safe_name}_report.html").write_text(html_content)
        return html_content

    def _dts_to_tree(self, dts: str) -> list[dict]:
        """Return a list of ``{"name": ..., "addr": ...}`` dicts for every ``name@addr`` node in *dts*."""
        return [
            {"name": f"{m.group(1)}@{m.group(2)}", "addr": m.group(2)}
            for m in re.finditer(r"(\w[\w-]*)@([0-9a-fA-F]+)\s*\{", dts)
        ]

    def _build_clock_data(self, topology: XsaTopology, cfg: dict) -> dict:
        """Assemble clock-topology data for the HTML report's D3 clock diagram."""
        clock_cfg = cfg.get("clock", {})
        return {
            "clkgens": [
                {"name": cg.name, "outputs": cg.output_clks} for cg in topology.clkgens
            ],
            "hmc_rx_ch": clock_cfg.get("hmc7044_rx_channel", "?"),
            "hmc_tx_ch": clock_cfg.get("hmc7044_tx_channel", "?"),
        }

    def _build_jesd_data(self, topology: XsaTopology) -> dict:
        """Assemble JESD204 path data for the HTML report's D3 JESD diagram."""
        return {
            "rx": [
                {"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes}
                for i in topology.jesd204_rx
            ],
            "tx": [
                {"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes}
                for i in topology.jesd204_tx
            ],
            "converters": [
                {"name": c.name, "type": c.ip_type} for c in topology.converters
            ],
        }

    def _build_wiring_data(
        self, topology: XsaTopology, cfg: dict, merged_dts: str
    ) -> dict:
        """Assemble the control-plane wiring graph for the D3 panel.

        Reuses :class:`adidt.xsa.viz.wiring_graph.WiringGraph.from_topology`
        so the HTML panel and the standalone DOT/D2 outputs always agree.
        """
        from .wiring_graph import WiringGraph

        graph = WiringGraph.from_topology(topology, cfg, merged_dts=merged_dts)
        return {
            "nodes": [
                {"id": n.label, "name": n.node_name, "kind": n.kind}
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source": e.src,
                    "target": e.dst,
                    "kind": e.kind,
                    "label": e.label,
                }
                for e in graph.edges
            ],
        }

    def _build_match_coverage(self, topology: XsaTopology, merged_dts: str) -> dict:
        """Compute how many parsed topology IPs appear by name in the merged DTS."""
        parsed = {
            "jesd204_rx": [i.name for i in topology.jesd204_rx],
            "jesd204_tx": [i.name for i in topology.jesd204_tx],
            "clkgens": [i.name for i in topology.clkgens],
            "converters": [i.name for i in topology.converters],
        }
        matched = {
            kind: [
                name
                for name in names
                if re.search(rf"\b{re.escape(name)}\b", merged_dts)
            ]
            for kind, names in parsed.items()
        }
        unmatched = {
            kind: [name for name in names if name not in set(matched[kind])]
            for kind, names in parsed.items()
        }
        total = sum(len(names) for names in parsed.values())
        matched_total = sum(len(names) for names in matched.values())
        unmatched_total = total - matched_total
        matched_pct = round((matched_total * 100.0 / total), 1) if total else 100.0
        unmatched_pct = round((unmatched_total * 100.0 / total), 1) if total else 0.0
        return {
            "total": total,
            "matched": matched_total,
            "unmatched": unmatched_total,
            "matched_pct": matched_pct,
            "unmatched_pct": unmatched_pct,
            "by_kind_total": {kind: len(names) for kind, names in parsed.items()},
            "by_kind_unmatched": unmatched,
        }

    def _json_safe(self, data) -> str:
        """Return JSON safe for inline JavaScript — escapes </script> sequence."""
        return json.dumps(data).replace("</", "<\\/")

    def _render_html(
        self, tree_data, clock_data, jesd_data, wiring_data, coverage_data, title: str
    ) -> str:
        """Build the full HTML string from pre-computed data sections."""
        safe_title = html.escape(title)
        tree_json = self._json_safe(tree_data)
        clock_json = self._json_safe(clock_data)
        jesd_json = self._json_safe(jesd_data)
        wiring_json = self._json_safe(wiring_data)
        coverage_json = self._json_safe(coverage_data)
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>ADI DTS Report: {safe_title}</title>
<style>
body{{font-family:monospace;background:#1e1e1e;color:#d4d4d4;margin:0}}
.panel{{padding:1em;border-bottom:1px solid #444}}
h2{{color:#569cd6}}
.adi-node{{color:#dcdcaa;font-weight:bold}}
.node-list li{{cursor:pointer;list-style:none;padding:2px 4px}}
.node-list li:hover{{background:#2d2d2d}}
#clock-svg,#jesd-svg{{width:100%;height:300px}}
#wiring-svg{{width:100%;height:480px}}
.wiring-toolbar{{margin-bottom:6px;font-size:12px}}
.wiring-toolbar label{{margin-right:12px;cursor:pointer}}
.wiring-toolbar input{{margin-right:4px;vertical-align:middle}}
.search{{background:#252526;color:#d4d4d4;border:1px solid #555;padding:4px;width:300px}}
details{{margin:8px 0;border:1px solid #3a3a3a;border-radius:4px;padding:6px;background:#232323}}
summary{{cursor:pointer;color:#9cdcfe;font-weight:bold}}
table{{width:100%;border-collapse:collapse;margin-top:8px}}
th,td{{border:1px solid #3a3a3a;padding:4px 6px;text-align:left;font-size:12px}}
th{{color:#dcdcaa}}
</style></head>
<body>
<div class="panel"><h2>DTS Node Tree — {safe_title}</h2>
<input class="search" type="text" id="search" placeholder="Search nodes..." oninput="filterNodes()">
<ul class="node-list" id="node-list"></ul></div>
<div class="panel"><h2>XSA Match Coverage</h2><div id="coverage-summary"></div></div>
<div class="panel"><h2>Details</h2>
  <details id="detail-coverage" open><summary>XSA Match Coverage</summary><div id="detail-coverage-body"></div></details>
  <details id="detail-topology"><summary>Parsed Topology</summary><div id="detail-topology-body"></div></details>
  <details id="detail-clocks"><summary>Clock References</summary><div id="detail-clocks-body"></div></details>
  <details id="detail-jesd"><summary>JESD Paths</summary><div id="detail-jesd-body"></div></details>
</div>
<div class="panel"><h2>Clock Topology</h2><svg id="clock-svg"></svg></div>
<div class="panel"><h2>JESD204 Data Path</h2><svg id="jesd-svg"></svg></div>
<div class="panel"><h2>Control-Plane Wiring</h2>
  <div class="wiring-toolbar">
    <label><input type="checkbox" data-kind="spi" checked>SPI</label>
    <label><input type="checkbox" data-kind="jesd" checked>JESD</label>
    <label><input type="checkbox" data-kind="gpio" checked>GPIO</label>
    <label><input type="checkbox" data-kind="irq" checked>IRQ</label>
    <label><input type="checkbox" data-kind="i2c" checked>I2C</label>
  </div>
  <svg id="wiring-svg"></svg>
</div>
<script>
{_D3_BUNDLE}
</script>
<script>
const treeData={tree_json};
const clockData={clock_json};
const jesdData={jesd_json};
const wiringData={wiring_json};
const coverageData={coverage_json};
function renderTree(data){{
  const list=document.getElementById("node-list");
  list.innerHTML="";
  data.forEach(n=>{{
    const li=document.createElement("li");
    const isAdi=n.name.includes("jesd")||n.name.includes("ad9081")||n.name.includes("ad9084");
    li.className=isAdi?"adi-node":"";
    li.textContent=n.name;
    list.appendChild(li);
  }});
}}
function filterNodes(){{
  const q=document.getElementById("search").value.toLowerCase();
  renderTree(treeData.filter(n=>n.name.toLowerCase().includes(q)));
}}

function renderTable(headers, rows){{
  const th=headers.map(h=>`<th>${{h}}</th>`).join("");
  const tr=rows.map(r=>`<tr>${{r.map(c=>`<td>${{c}}</td>`).join("")}}</tr>`).join("");
  return `<table><thead><tr>${{th}}</tr></thead><tbody>${{tr}}</tbody></table>`;
}}

function renderDetails(){{
  const coverageBody=document.getElementById("detail-coverage-body");
  const unmatchedList=Object.entries(coverageData.by_kind_unmatched)
    .flatMap(([k,v])=>v.map(name=>`${{k}}: ${{name}}`));
  coverageBody.innerHTML = `
    <div>Matched: ${{coverageData.matched}} / ${{coverageData.total}} (${{coverageData.matched_pct}}%)</div>
    <div>Unmatched: ${{coverageData.unmatched}} / ${{coverageData.total}} (${{coverageData.unmatched_pct}}%)</div>
    <div style="margin-top:8px;">Unmatched entries:</div>
    <ul>${{unmatchedList.map(v=>`<li>${{v}}</li>`).join("")}}</ul>
  `;

  const topologyRows = [
    ["JESD RX", jesdData.rx.length],
    ["JESD TX", jesdData.tx.length],
    ["Converters", jesdData.converters.length],
    ["Clockgens", (clockData.clkgens || []).length],
  ];
  document.getElementById("detail-topology-body").innerHTML = renderTable(
    ["Type", "Count"], topologyRows
  );

  const clockRows = (clockData.clkgens || []).flatMap(cg =>
    (cg.outputs || []).map(out => [cg.name, out])
  );
  document.getElementById("detail-clocks-body").innerHTML = clockRows.length
    ? renderTable(["Clockgen", "Output Net"], clockRows)
    : "<div>No clock outputs parsed.</div>";

  const jesdRows = [
    ...jesdData.rx.map(r => ["RX", r.name, r.addr || "-", r.lanes || "-"]),
    ...jesdData.tx.map(t => ["TX", t.name, t.addr || "-", t.lanes || "-"]),
  ];
  document.getElementById("detail-jesd-body").innerHTML = jesdRows.length
    ? renderTable(["Dir", "Name", "Addr", "Lanes"], jesdRows)
    : "<div>No JESD cores parsed.</div>";
}}

renderTree(treeData);
(function(){{
  const root=document.getElementById("coverage-summary");
  const rows=[
    `Matched: ${{coverageData.matched}} / ${{coverageData.total}} (${{coverageData.matched_pct}}%)`,
    `Unmatched: ${{coverageData.unmatched}} / ${{coverageData.total}} (${{coverageData.unmatched_pct}}%)`
  ];
  const unmatchedList=Object.entries(coverageData.by_kind_unmatched)
    .flatMap(([k,v])=>v.map(name=>`${{k}}: ${{name}}`));
  root.innerHTML = `
    <div>${{rows[0]}}</div>
    <div>${{rows[1]}}</div>
    <div style="margin-top:8px;">Unmatched entries:</div>
    <ul>${{unmatchedList.map(v=>`<li>${{v}}</li>`).join("")}}</ul>
  `;
}})();
renderDetails();
(function(){{
  const svg=d3.select("#clock-svg");
  const bW=160,bH=40,gap=20;
  (clockData.clkgens||[]).forEach((cg,i)=>{{
    const x=gap+i*(bW+gap);
    svg.append("rect").attr("x",x).attr("y",10).attr("width",bW).attr("height",bH).attr("fill","#264f78").attr("stroke","#569cd6");
    svg.append("text").attr("x",x+bW/2).attr("y",35).attr("text-anchor","middle").attr("fill","#d4d4d4").attr("font-size","11px").text(cg.name);
    (cg.outputs||[]).forEach((out,j)=>{{
      svg.append("text").attr("x",x+bW/2).attr("y",75+j*18).attr("text-anchor","middle").attr("fill","#9cdcfe").attr("font-size","10px").text(out);
    }});
  }});
}})();
(function(){{
  const svg=d3.select("#jesd-svg");
  const bW=180,bH=50,gap=30,y=20;
  const boxes=[...jesdData.rx.map(r=>{{return{{...r,kind:"RX"}}}}),
               ...jesdData.converters.map(c=>{{return{{...c,kind:"CONV"}}}}),
               ...jesdData.tx.map(t=>{{return{{...t,kind:"TX"}}}})];
  boxes.forEach((b,i)=>{{
    const x=gap+i*(bW+gap);
    const color=b.kind==="RX"?"#1e4d78":b.kind==="TX"?"#4d1e78":"#264f1e";
    svg.append("rect").attr("x",x).attr("y",y).attr("width",bW).attr("height",bH).attr("fill",color).attr("stroke","#569cd6");
    svg.append("text").attr("x",x+bW/2).attr("y",y+20).attr("text-anchor","middle").attr("fill","#d4d4d4").attr("font-size","11px").text(b.name||b.type);
    svg.append("text").attr("x",x+bW/2).attr("y",y+38).attr("text-anchor","middle").attr("fill","#9cdcfe").attr("font-size","10px").text(b.lanes?b.lanes+" lanes":b.kind);
    if(i>0)svg.append("line").attr("x1",x-gap).attr("y1",y+bH/2).attr("x2",x).attr("y2",y+bH/2).attr("stroke","#569cd6");
  }});
}})();
(function(){{
  const KIND_COLOR={{spi:"#4ac4d8",jesd:"#44cc44",gpio:"#cc9944",irq:"#cc4444",i2c:"#a04ac4"}};
  const NODE_COLOR={{
    spi_master:"#2a4d6e",gpio_controller:"#6e4d2a",i2c_master:"#5a2a6e",
    interrupt_controller:"#6e2a2a",ps_clock:"#7a3800",clock_chip:"#1a3d5c",
    xcvr:"#4a1a5c",jesd:"#1a4a20",clkgen:"#1a4a4a",converter:"#5c1a1a",
    dma:"#3a3a3a",other:"#2a2a2a"
  }};
  const svg=d3.select("#wiring-svg");
  const W=svg.node().getBoundingClientRect().width||900;
  const H=480;
  svg.attr("viewBox",`0 0 ${{W}} ${{H}}`);
  let active=new Set(["spi","jesd","gpio","irq","i2c"]);
  const allEdges=(wiringData.edges||[]).map(e=>({{...e}}));
  const allNodes=(wiringData.nodes||[]).map(n=>({{...n}}));
  const nodesById=new Map(allNodes.map(n=>[n.id,n]));
  const linkGroup=svg.append("g").attr("class","links");
  const labelGroup=svg.append("g").attr("class","edge-labels");
  const nodeGroup=svg.append("g").attr("class","nodes");
  const sim=d3.forceSimulation(allNodes)
    .force("link",d3.forceLink([]).id(d=>d.id).distance(110).strength(0.6))
    .force("charge",d3.forceManyBody().strength(-260))
    .force("center",d3.forceCenter(W/2,H/2));
  function refresh(){{
    const visEdges=allEdges.filter(e=>active.has(e.kind))
      .map(e=>({{...e,source:nodesById.get(e.source),target:nodesById.get(e.target)}}))
      .filter(e=>e.source&&e.target);
    sim.force("link").links(visEdges);
    sim.alpha(0.6).restart();
    const link=linkGroup.selectAll("line").data(visEdges,d=>d.source.id+">"+d.target.id+":"+d.kind);
    link.exit().remove();
    link.enter().append("line").attr("stroke-width",1.5)
      .merge(link)
      .attr("stroke",d=>KIND_COLOR[d.kind]||"#888")
      .attr("stroke-dasharray",d=>d.kind==="irq"?"4,3":null);
    const elabel=labelGroup.selectAll("text").data(visEdges.filter(e=>e.label),d=>d.source.id+">"+d.target.id+":"+d.kind+":"+d.label);
    elabel.exit().remove();
    elabel.enter().append("text").attr("font-size","9px").attr("fill","#9cdcfe").attr("text-anchor","middle")
      .merge(elabel).text(d=>d.label);
    const node=nodeGroup.selectAll("g.node").data(allNodes,d=>d.id);
    const nEnter=node.enter().append("g").attr("class","node");
    nEnter.append("rect").attr("x",-50).attr("y",-12).attr("width",100).attr("height",24).attr("rx",4).attr("stroke","#000");
    nEnter.append("text").attr("text-anchor","middle").attr("dy","0.35em").attr("fill","#fff").attr("font-size","10px");
    nEnter.merge(node).select("rect").attr("fill",d=>NODE_COLOR[d.kind]||"#2a2a2a");
    nEnter.merge(node).select("text").text(d=>d.id);
  }}
  sim.on("tick",()=>{{
    linkGroup.selectAll("line")
      .attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
      .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
    labelGroup.selectAll("text")
      .attr("x",d=>(d.source.x+d.target.x)/2)
      .attr("y",d=>(d.source.y+d.target.y)/2-3);
    nodeGroup.selectAll("g.node").attr("transform",d=>`translate(${{d.x}},${{d.y}})`);
  }});
  document.querySelectorAll(".wiring-toolbar input").forEach(cb=>{{
    cb.addEventListener("change",()=>{{
      const k=cb.dataset.kind;
      if(cb.checked)active.add(k);else active.delete(k);
      refresh();
    }});
  }});
  refresh();
}})();
</script></body></html>"""
