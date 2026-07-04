"""Generate Synod architecture diagram with graphviz."""

from graphviz import Digraph

BG = "#12121a"
NODE_BORDER = "#3a3a4a"
TEXT = "#eae6f0"
EDGE = "#7a7690"

g = Digraph("Synod", format="png")
g.attr(rankdir="TB", bgcolor=BG, fontname="Georgia", fontcolor=TEXT,
       ranksep="0.7", nodesep="0.55", pad="0.5")
g.attr("node", fontname="Georgia", fontsize="12", shape="box",
       style="rounded,filled", color=NODE_BORDER, fontcolor=TEXT, penwidth="1.2")
g.attr("edge", fontname="Georgia", fontsize="10", color=EDGE, fontcolor=EDGE,
       penwidth="1.1", arrowsize="0.7")

g.node("user", "User / Client", shape="oval", fillcolor="#1c1c28")
g.node("orch", "Council\n(orchestrator)", fillcolor="#3d4a7a", fontcolor="#f0f0f5")
g.node("cartographer", "Cartographer\nmaps structure/dependencies",
       fillcolor="#5b4a7a", fontcolor="#f0f0f5")

with g.subgraph(name="cluster_parallel") as c:
    c.attr(label="With Cartographer context", style="rounded", color="#8a7ba0",
           fontsize="12", fontcolor="#b8aed0", bgcolor="#181822")
    c.node("inspector", "Inspector\ncode quality", fillcolor="#3d6b52", fontcolor="#f0f0f5")
    c.node("sentinel", "Sentinel\nsecurity (CWE)", fillcolor="#7a3d3d", fontcolor="#f0f0f5")

g.node("gate", "severity\nhigh/critical?", shape="diamond", fillcolor="#7a6438", fontcolor="#f0f0f5")

with g.subgraph(name="cluster_loop") as c:
    c.attr(label="Optional fix loop (max 2 iter)", style="rounded", color="#a06a8a",
           fontsize="12", fontcolor="#c99cb8", bgcolor="#181822")
    c.node("smith", "Smith\ngenerates fix", fillcolor="#6b3d5e", fontcolor="#f0f0f5")
    c.node("sentinel2", "Sentinel\nvalidates fix", fillcolor="#7a3d3d", fontcolor="#f0f0f5")

g.node("arbiter", "Arbiter\ndedup + consensus + evidence check",
       fillcolor="#8a7238", fontcolor="#f0f0f5")
g.node("mem", "Working Memory\n(in-memory dict)", fillcolor="#1c1c28")
g.node("report", "Report\nFinding / Detail / Impact / Proposal",
       shape="oval", fillcolor="#1c1c28")

g.edge("user", "orch")
g.edge("orch", "cartographer")
g.edge("cartographer", "inspector")
g.edge("cartographer", "sentinel")
g.edge("inspector", "gate")
g.edge("sentinel", "gate")
g.edge("gate", "smith", label="yes")
g.edge("smith", "sentinel2")
g.edge("sentinel2", "smith", label="retry (max 2x)", style="dashed")
g.edge("sentinel2", "arbiter")
g.edge("gate", "arbiter", label="no")
g.edge("orch", "mem", style="dotted")
g.edge("arbiter", "report")

g.render("docs/architecture", cleanup=True)
print("done")
