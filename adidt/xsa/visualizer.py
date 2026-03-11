# adidt/xsa/visualizer.py
import html
import json
import re
from pathlib import Path
from typing import Any

from .topology import XsaTopology

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
        if not _D3_BUNDLE:
            raise RuntimeError(
                "D3 bundle missing — run scripts/embed_d3.py to generate "
                "adidt/xsa/d3_bundle.js"
            )
        tree_data = self._dts_to_tree(merged_dts)
        clock_data = self._build_clock_data(topology, cfg)
        jesd_data = self._build_jesd_data(topology)
        html_content = self._render_html(tree_data, clock_data, jesd_data, name)
        safe_name = re.sub(r"[^\w\-.]", "_", name)
        (output_dir / f"{safe_name}_report.html").write_text(html_content)
        return html_content

    def _dts_to_tree(self, dts: str) -> list[dict]:
        return [
            {"name": f"{m.group(1)}@{m.group(2)}", "addr": m.group(2)}
            for m in re.finditer(r"(\w[\w-]*)@([0-9a-fA-F]+)\s*\{", dts)
        ]

    def _build_clock_data(self, topology: XsaTopology, cfg: dict) -> dict:
        clock_cfg = cfg.get("clock", {})
        return {
            "clkgens": [{"name": cg.name, "outputs": cg.output_clks} for cg in topology.clkgens],
            "hmc_rx_ch": clock_cfg.get("hmc7044_rx_channel", "?"),
            "hmc_tx_ch": clock_cfg.get("hmc7044_tx_channel", "?"),
        }

    def _build_jesd_data(self, topology: XsaTopology) -> dict:
        return {
            "rx": [{"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes} for i in topology.jesd204_rx],
            "tx": [{"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes} for i in topology.jesd204_tx],
            "converters": [{"name": c.name, "type": c.ip_type} for c in topology.converters],
        }

    def _json_safe(self, data) -> str:
        """Return JSON safe for inline JavaScript — escapes </script> sequence."""
        return json.dumps(data).replace("</", "<\\/")

    def _render_html(self, tree_data, clock_data, jesd_data, title: str) -> str:
        safe_title = html.escape(title)
        tree_json = self._json_safe(tree_data)
        clock_json = self._json_safe(clock_data)
        jesd_json = self._json_safe(jesd_data)
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
.search{{background:#252526;color:#d4d4d4;border:1px solid #555;padding:4px;width:300px}}
</style></head>
<body>
<div class="panel"><h2>DTS Node Tree — {safe_title}</h2>
<input class="search" type="text" id="search" placeholder="Search nodes..." oninput="filterNodes()">
<ul class="node-list" id="node-list"></ul></div>
<div class="panel"><h2>Clock Topology</h2><svg id="clock-svg"></svg></div>
<div class="panel"><h2>JESD204 Data Path</h2><svg id="jesd-svg"></svg></div>
<script>
{_D3_BUNDLE}
</script>
<script>
const treeData={tree_json};
const clockData={clock_json};
const jesdData={jesd_json};
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
renderTree(treeData);
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
</script></body></html>"""
