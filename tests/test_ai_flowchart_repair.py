from __future__ import annotations

from openrpa.bridge import _repair_flowchart_node_id_collisions
from openrpa.model import validate_workflow


def test_ai_flowchart_action_node_collision_is_renamed_and_edges_rewritten():
    graph = {
        "start": "start",
        "nodes": [
            {"id": "start", "kind": "start"},
            {"id": "log_activity", "kind": "action", "activity": {"id": "log_activity", "type": "log", "message": "hello"}},
            {"id": "end", "kind": "end"},
        ],
        "transitions": [{"from": "start", "to": "log_activity"}, {"from": "log_activity", "to": "end"}],
    }

    warnings = _repair_flowchart_node_id_collisions(graph)

    assert warnings == ["Adjusted a flowchart node ID that collided with an activity ID; activity IDs were preserved."]
    assert graph["nodes"][1]["id"] == "node-2"
    assert graph["nodes"][1]["activity"]["id"] == "log_activity"
    assert graph["transitions"] == [{"from": "start", "to": "node-2"}, {"from": "node-2", "to": "end"}]
    workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "AI Draft", "variables": [], "arguments": [], "activities": [], "executionModel": "flowchart", "flowchart": graph}
    assert validate_workflow(workflow, {"Main"}) == []


def test_ai_flowchart_repair_leaves_unambiguous_graph_unchanged():
    graph = {"start": "start", "nodes": [{"id": "start", "kind": "start"}, {"id": "action-node", "kind": "action", "activity": {"id": "log", "type": "log", "message": "hello"}}, {"id": "end", "kind": "end"}], "transitions": []}

    assert _repair_flowchart_node_id_collisions(graph) == []
    assert graph["nodes"][1]["id"] == "action-node"
