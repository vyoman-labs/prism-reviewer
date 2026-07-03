"""
prism_reviewer.agents.graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Assembles and compiles the PrismReviewer LangGraph ``StateGraph``.

Graph topology
--------------
::

    START
      └─► build_context_node
            │
            ├─[Send]─► warden_node    ─┐
            ├─[Send]─► architect_node  ├── reducer merges raw_findings
            └─[Send]─► inspector_node ─┘
                              │
                        verifier_node   (hallucination guard + dedup)
                              │
                        aggregator_node (sort + Markdown render)
                              │
                            END

Fan-out is implemented using ``langgraph.constants.Send`` objects returned
from ``_fan_out_router``.  Each ``Send`` delivers the full current state to
its target node independently, enabling true parallel execution.

The three agent nodes feed back into ``verifier_node`` via a shared join.
LangGraph waits for all three branches to complete before invoking the
verifier, at which point the ``operator.add`` reducer on ``raw_findings``
has already merged all three lists.
"""

from typing import List

from langgraph.types import Send
from langgraph.graph import END, START, StateGraph

from ..core.logger import get_logger
from .aggregator import aggregator_node
from .nodes import architect_node, build_context_node, inspector_node, warden_node
from .state import ReviewState
from .verifier import verifier_node

logger = get_logger("prism_reviewer.agents.graph")


def _fan_out_router(state: ReviewState) -> List[Send]:
    """
    Conditional edge router that fans out to all three agent nodes in parallel.
    For large PRs, splits and sends individual review regions to the agents.

    Returns a list of ``Send`` objects targeting ``"warden"``,
    ``"architect"``, and ``"inspector"`` nodes.
    """
    regions = state.get("regions", [])
    if not regions:
        # Fallback if no regions were built (e.g. empty diff)
        return [
            Send("warden", state),
            Send("architect", state),
            Send("inspector", state),
        ]

    sends: List[Send] = []
    for region in regions:
        # Create a customized state payload for this region branch
        region_state = dict(state)
        region_state["git_diff"] = region["diff"]
        region_state["current_region"] = region
        # Filter ast_map to only include files in this region
        full_ast_map = state.get("ast_map", {})
        region_state["ast_map"] = {
            k: v for k, v in full_ast_map.items() if k in region["files"]
        }

        sends.append(Send("warden", region_state))
        sends.append(Send("architect", region_state))
        sends.append(Send("inspector", region_state))

    return sends


def build_graph():
    """
    Assembles and compiles the PrismReviewer ``StateGraph``.

    Call this once at startup and reuse the compiled graph across review runs.
    The compiled graph is thread-safe and can be invoked concurrently.

    Returns:
        A compiled LangGraph ``CompiledGraph`` instance ready for
        ``.stream()`` or ``.invoke()`` calls.
    """
    builder: StateGraph = StateGraph(ReviewState)

    # Register all nodes
    builder.add_node("build_context", build_context_node)
    builder.add_node("warden",        warden_node)
    builder.add_node("architect",     architect_node)
    builder.add_node("inspector",     inspector_node)
    builder.add_node("verifier",      verifier_node)
    builder.add_node("aggregator",    aggregator_node)

    # Linear entry: START → context builder
    builder.add_edge(START, "build_context")

    # Fan-out: context builder → all three agents in parallel
    builder.add_conditional_edges("build_context", _fan_out_router)

    # Fan-in: all three agents → verifier (LangGraph joins automatically)
    builder.add_edge("warden",    "verifier")
    builder.add_edge("architect", "verifier")
    builder.add_edge("inspector", "verifier")

    # Linear exit: verifier → aggregator → END
    builder.add_edge("verifier",  "aggregator")
    builder.add_edge("aggregator", END)

    compiled = builder.compile()
    logger.info("[agents.graph] Graph compiled successfully")
    return compiled
