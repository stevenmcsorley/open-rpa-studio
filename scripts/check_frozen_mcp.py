"""Acceptance check for the frozen MCP bridge's live workflow staging path."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    bridge = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="openrpa-live-mcp-check-") as directory:
        root = Path(directory)
        workflow_dir = root / "workflows"
        workflow_dir.mkdir()
        project = {
            "format": "openrpa.project", "formatVersion": 1,
            "name": "MCP Acceptance", "main": "Main",
            "workflows": {"Main": "workflows/main.workflow.json"},
        }
        main_workflow = {
            "format": "openrpa.workflow", "formatVersion": 1,
            "name": "Main", "executionModel": "sequence",
            "arguments": [], "variables": [], "activities": [],
        }
        (root / "project.json").write_text(json.dumps(project), encoding="utf-8")
        (workflow_dir / "main.workflow.json").write_text(json.dumps(main_workflow), encoding="utf-8")
        draft = {
            **main_workflow, "name": "Live acceptance",
            "activities": [
                {"id": "log-live", "type": "log", "level": "info", "message": "Visible staged workflow"},
                {"id": "aria-snapshot", "type": "browser_accessibility_snapshot", "timeoutSeconds": 15, "maxOutputChars": 50000, "result": "accessibilitySnapshot"},
            ],
        }
        env = {**os.environ, "OPENRPA_ACTIVE_PROJECT_FILE": str(root / ".test-active-project.json")}

        def call(request: dict, flags: tuple[str, ...] = ()) -> dict:
            process = subprocess.Popen(
                [str(bridge), "mcp", str(root), "--allow-edit", *flags],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", env=env,
            )
            stdout, stderr = process.communicate(json.dumps(request) + "\n", timeout=45)
            if process.returncode:
                raise RuntimeError(f"Frozen bridge exited {process.returncode}: {stderr[-2000:]}")
            lines = [line for line in stdout.splitlines() if line.strip()]
            if not lines:
                raise RuntimeError(f"Frozen bridge returned no MCP response. stderr: {stderr[-2000:]}")
            return json.loads(lines[-1])

        listed = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool.get("name") for tool in listed.get("result", {}).get("tools", [])}
        expected_inspection_tools = {
            "openrpa_desktop_status",
            "openrpa_list_desktop_windows",
            "openrpa_list_desktop_controls",
        }
        if not expected_inspection_tools <= tool_names:
            raise RuntimeError(f"Frozen MCP desktop inspection tools missing: {sorted(expected_inspection_tools - tool_names)}")
        expected_live_browser_tools={"openrpa_browser_open","openrpa_browser_navigate","openrpa_browser_snapshot","openrpa_browser_screenshot","openrpa_browser_action","openrpa_browser_start_recording","openrpa_browser_stop_recording","openrpa_browser_close"}
        if "openrpa_desktop_action" in tool_names:
            raise RuntimeError("Frozen MCP exposed live desktop actions without run/desktop startup grants")
        if expected_live_browser_tools & tool_names:
            raise RuntimeError("Frozen MCP exposed live browser actions without run/network/desktop startup grants")
        granted_listing=call({"jsonrpc":"2.0","id":7,"method":"tools/list","params":{}},("--allow-run","--allow-network","--allow-desktop"))
        granted_names={tool.get("name") for tool in granted_listing.get("result",{}).get("tools",[])}
        if not expected_live_browser_tools<=granted_names:
            raise RuntimeError(f"Frozen MCP live browser tools missing under explicit grants: {sorted(expected_live_browser_tools-granted_names)}")
        browser_action=next(tool for tool in granted_listing.get("result",{}).get("tools",[]) if tool.get("name")=="openrpa_browser_action")
        browser_schema=browser_action.get("inputSchema",{})
        browser_operations=set(browser_schema.get("properties",{}).get("action",{}).get("enum",[]))
        if "select_many" not in browser_operations or browser_schema.get("properties",{}).get("values",{}).get("maxItems")!=100:
            raise RuntimeError("Frozen MCP browser multi-selection action or bounded values schema is missing")
        if "openrpa_desktop_action" not in granted_names:
            raise RuntimeError("Frozen MCP live desktop action is missing under run/desktop grants")
        desktop_action=next(tool for tool in granted_listing.get("result",{}).get("tools",[]) if tool.get("name")=="openrpa_desktop_action")
        desktop_schema=desktop_action.get("inputSchema",{})
        desktop_operations=set(desktop_schema.get("properties",{}).get("action",{}).get("enum",[]))
        required_operations={"launch_application","wait_window","close_window"}
        if not required_operations<=desktop_operations:
            raise RuntimeError(f"Frozen MCP desktop lifecycle actions missing: {sorted(required_operations-desktop_operations)}")
        if "drag" not in desktop_operations or "read_grid" not in desktop_operations:
            raise RuntimeError("Frozen MCP lacks accessible drag or grid-read desktop actions")
        if "select_many" not in desktop_operations:
            raise RuntimeError("Frozen MCP lacks accessible multi-item list selection")
        if "set_range_value" not in desktop_operations:
            raise RuntimeError("Frozen MCP lacks bounded native slider/spinner value setting")
        if "scroll_into_view" not in desktop_operations:
            raise RuntimeError("Frozen MCP lacks native off-screen desktop scrolling")
        if desktop_schema.get("properties", {}).get("values", {}).get("maxItems") != 100:
            raise RuntimeError("Frozen MCP multi-item selection is not bounded to 100 names")
        if set(desktop_schema.get("properties", {}).get("mode", {}).get("enum", [])) != {"replace", "add", "remove"}:
            raise RuntimeError("Frozen MCP list selection modes are missing or invalid")
        if desktop_schema.get("properties",{}).get("maxOutputChars",{}).get("maximum")!=500_000:
            raise RuntimeError("Frozen MCP desktop grid output is not bounded")
        if desktop_schema.get("properties",{}).get("arguments",{}).get("maxItems")!=32:
            raise RuntimeError("Frozen MCP desktop process arguments are not bounded")
        range_workflow={**main_workflow,"name":"Desktop range value acceptance","activities":[{"id":"set-zoom","type":"desktop_ui_set_range_value","windowTitle":"Acceptance Editor","automationId":"zoom","controlType":"Slider","value":0.75}]}
        valid_range=call({"jsonrpc":"2.0","id":23,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{range_workflow["name"]:range_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_range.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected a bounded UIA range value workflow: {valid_range}")
        spin_range={**range_workflow,"activities":[{**range_workflow["activities"][0],"controlType":"Spin Button","value":3}]}
        valid_spin=call({"jsonrpc":"2.0","id":27,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{spin_range["name"]:spin_range}}}}).get("result",{}).get("structuredContent",{})
        if not valid_spin.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected the AT-SPI Spin Button type: {valid_spin}")
        invalid_range={**range_workflow,"activities":[{**range_workflow["activities"][0],"controlType":"Button"}]}
        rejected_range=call({"jsonrpc":"2.0","id":24,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_range["name"]:invalid_range}}}}).get("result",{}).get("structuredContent",{})
        if rejected_range.get("valid") or "desktop-uia-range-type" not in {problem.get("code") for problem in rejected_range.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject an incompatible range control type: {rejected_range}")
        nonnumeric_range={**range_workflow,"activities":[{**range_workflow["activities"][0],"value":"not numeric"}]}
        rejected_range_value=call({"jsonrpc":"2.0","id":26,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{nonnumeric_range["name"]:nonnumeric_range}}}}).get("result",{}).get("structuredContent",{})
        if rejected_range_value.get("valid") or "desktop-uia-range-value" not in {problem.get("code") for problem in rejected_range_value.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject a nonnumeric range value: {rejected_range_value}")
        blocked_browser=call({"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"openrpa_browser_open","arguments":{"url":"http://127.0.0.1/private"}}},("--allow-run","--allow-network","--allow-desktop"))
        blocked_result=blocked_browser.get("result",{})
        if not blocked_result.get("isError") or "non-public" not in blocked_result.get("content",[{}])[0].get("text",""):
            raise RuntimeError(f"Frozen MCP browser tools failed to block a loopback destination: {blocked_browser}")

        catalog = call({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "openrpa_activity_catalog", "arguments": {}},
        }).get("result", {}).get("structuredContent", {}).get("activities", [])
        catalog_by_type = {activity.get("type"): activity for activity in catalog}
        expected_browser_activities = {"browser_launch", "browser_scroll", "browser_extract_records", "browser_hover", "browser_press", "browser_new_tab", "browser_capture_popup", "browser_switch_tab", "browser_close_tab", "browser_upload", "browser_download", "browser_wait_response", "browser_accessibility_snapshot", "browser_select_many"}
        expected_desktop_activities = {"desktop_ui_select", "desktop_ui_select_many", "desktop_ui_check", "desktop_ui_uncheck", "desktop_ui_invoke", "desktop_ui_press", "desktop_ui_expand", "desktop_ui_collapse", "desktop_ui_drag", "desktop_ui_grid_read", "desktop_ocr_click", "desktop_window_wait", "desktop_window_activate", "desktop_window_minimize", "desktop_window_restore", "desktop_window_close"}
        if not expected_browser_activities <= catalog_by_type.keys():
            raise RuntimeError(f"Frozen MCP browser activities missing: {sorted(expected_browser_activities - catalog_by_type.keys())}")
        if not expected_desktop_activities <= catalog_by_type.keys():
            raise RuntimeError(f"Frozen MCP desktop accessibility activities missing: {sorted(expected_desktop_activities - catalog_by_type.keys())}")
        response_defaults=catalog_by_type["browser_wait_response"].get("defaults",{})
        if response_defaults.get("maxResponseBytes")!=500000:
            raise RuntimeError(f"Frozen MCP bounded JSON response mapping default is missing: {response_defaults}")
        if response_defaults.get("discoverJsonSchema") is not False or response_defaults.get("schemaResult")!="responseSchema":
            raise RuntimeError(f"Frozen MCP value-free JSON schema discovery defaults are missing: {response_defaults}")
        response_mapping={"id":"wait-json","type":"browser_wait_response","urlContains":"/api/items","method":"get","maxResponseBytes":250000,"jsonMapping":{"itemsPointer":"/data/items","result":"mappedItems","maxItems":250,"fields":[{"name":"id","path":"/id"},{"name":"label","path":"/label"}]},"result":"responseMetadata"}
        response_workflow={**main_workflow,"name":"Bounded API response mapping acceptance","activities":[response_mapping]}
        response_validation=call({"jsonrpc":"2.0","id":23,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{response_workflow["name"]:response_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not response_validation.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected bounded JSON response mapping: {response_validation}")
        invalid_response={**response_workflow,"activities":[{**response_mapping,"jsonMapping":{"itemsPointer":"/data/~2items","result":"responseMetadata","maxItems":250,"fields":[{"name":"id","path":"/id"}]}}]}
        response_rejection=call({"jsonrpc":"2.0","id":24,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_response["name"]:invalid_response}}}}).get("result",{}).get("structuredContent",{})
        if response_rejection.get("valid") or not {"browser-response-pointer","browser-response-mapping-result-conflict"}<={problem.get("code") for problem in response_rejection.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject malformed JSON response mapping: {response_rejection}")
        schema_activity={"id":"inspect-json","type":"browser_wait_response","urlContains":"/api/items","discoverJsonSchema":True,"schemaResult":"responseShape","result":"metadata"}
        schema_workflow={**main_workflow,"name":"Value-free API schema discovery acceptance","activities":[schema_activity]}
        schema_validation=call({"jsonrpc":"2.0","id":25,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{schema_workflow["name"]:schema_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not schema_validation.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected value-free JSON schema discovery: {schema_validation}")
        invalid_schema={**schema_workflow,"activities":[{**schema_activity,"schemaResult":"metadata"}]}
        schema_rejection=call({"jsonrpc":"2.0","id":26,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_schema["name"]:invalid_schema}}}}).get("result",{}).get("structuredContent",{})
        if schema_rejection.get("valid") or "browser-response-schema-result-conflict" not in {problem.get("code") for problem in schema_rejection.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject a conflicting schema output variable: {schema_rejection}")
        extract_defaults=catalog_by_type["browser_extract_records"].get("defaults",{})
        if extract_defaults.get("append") is not False or extract_defaults.get("deduplicateBy")!=[] or extract_defaults.get("maxTotalRecords")!=10000 or extract_defaults.get("maxTotalOutputChars")!=5000000:
            raise RuntimeError(f"Frozen MCP browser extraction does not expose bounded page accumulation defaults: {extract_defaults}")
        scroll_defaults=catalog_by_type["browser_scroll"].get("defaults",{})
        if scroll_defaults.get("containerSelector")!="":
            raise RuntimeError(f"Frozen MCP browser scrolling does not default to page scope with optional container selection: {scroll_defaults}")
        scroll_workflow={**main_workflow,"name":"Nested browser scroll acceptance","activities":[{"id":"scroll-feed","type":"browser_scroll","containerSelector":"#results-feed","toBottom":True,"maxSteps":25,"result":"scrollProgress"}]}
        scroll_validation=call({"jsonrpc":"2.0","id":20,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{scroll_workflow["name"]:scroll_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not scroll_validation.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected an explicitly scoped browser scroll: {scroll_validation}")
        invalid_scroll={**scroll_workflow,"activities":[{**scroll_workflow["activities"][0],"containerSelector":" "}]}
        scroll_rejection=call({"jsonrpc":"2.0","id":21,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_scroll["name"]:invalid_scroll}}}}).get("result",{}).get("structuredContent",{})
        if scroll_rejection.get("valid") or "browser-scroll-container" not in {problem.get("code") for problem in scroll_rejection.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject a malformed browser scroll selector: {scroll_rejection}")
        append_activity={"id":"extract-page","type":"browser_extract_records","selectorKind":"css","selector":"article.book","fields":[{"name":"title","selector":"h2","source":"text","required":True},{"name":"url","selector":"a","source":"attribute","attribute":"href"}],"append":True,"deduplicateBy":["url"],"maxTotalRecords":1200,"maxTotalOutputChars":750000,"result":"books"}
        append_workflow={**main_workflow,"name":"Paginated card accumulation acceptance","activities":[append_activity]}
        append_validation=call({"jsonrpc":"2.0","id":18,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{append_workflow["name"]:append_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not append_validation.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected bounded browser record accumulation: {append_validation}")
        invalid_dedup={**append_workflow,"activities":[{**append_activity,"deduplicateBy":["missing-field"]}]}
        dedup_rejection=call({"jsonrpc":"2.0","id":22,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_dedup["name"]:invalid_dedup}}}}).get("result",{}).get("structuredContent",{})
        if dedup_rejection.get("valid") or "browser-extract-deduplicate" not in {problem.get("code") for problem in dedup_rejection.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP failed to reject an unmapped browser deduplication key: {dedup_rejection}")
        invalid_append={**append_workflow,"activities":[{**append_activity,"maxTotalRecords":50001}]}
        append_rejection=call({"jsonrpc":"2.0","id":19,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_append["name"]:invalid_append}}}}).get("result",{}).get("structuredContent",{})
        if append_rejection.get("valid") or "browser-extract-total-limit" not in {problem.get("code") for problem in append_rejection.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP did not enforce browser extraction aggregate limits: {append_rejection}")
        ocr_workflow={**main_workflow,"name":"Bounded desktop OCR acceptance","activities":[{"id":"ocr-click","type":"desktop_ocr_click","windowTitle":"Acceptance Window","processId":1234,"text":"Continue safely","confidenceThreshold":80,"timeoutSeconds":15,"result":"ocrMatch"}]}
        valid_ocr=call({"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{ocr_workflow["name"]:ocr_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_ocr.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected scoped OCR desktop clicking: {valid_ocr}")
        invalid_ocr={**ocr_workflow,"activities":[{**ocr_workflow["activities"][0],"confidenceThreshold":101}]}
        rejected_ocr=call({"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_ocr["name"]:invalid_ocr}}}}).get("result",{}).get("structuredContent",{})
        if rejected_ocr.get("valid") or "desktop-ocr-confidence" not in {item.get("code") for item in rejected_ocr.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP did not reject an invalid OCR confidence threshold: {rejected_ocr}")
        if catalog_by_type["browser_launch"].get("defaults", {}).get("headless") is not False:
            raise RuntimeError("Frozen MCP Browser Launch does not default to a visible window")
        if catalog_by_type["browser_launch"].get("defaults", {}).get("profileName") != "" or catalog_by_type["browser_launch"].get("conditionalPermissions") != {"profileName=non-empty":["desktop"]}:
            raise RuntimeError("Frozen MCP does not advertise isolated persistent browser profiles and their desktop permission gate")
        if catalog_by_type.get("browser_click", {}).get("defaults", {}).get("selectorHealing") != "off":
            raise RuntimeError("Frozen MCP browser selector recovery is not advertised as opt-in")

        key_workflow = {
            **main_workflow, "name": "UI key acceptance",
            "activities": [{"id": "press-enter", "type": "desktop_ui_press",
                            "windowTitle": "Acceptance Editor", "name": "Document",
                            "automationId": "document", "controlType": "Edit", "key": "Enter"}],
        }
        valid_keys = call({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "openrpa_validate_workflow_drafts",
                       "arguments": {"workflows": {key_workflow["name"]: key_workflow}}},
        }).get("result", {}).get("structuredContent", {})
        if not valid_keys.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected a supported desktop key workflow: {valid_keys}")
        grid_workflow={**main_workflow,"name":"UI grid acceptance","activities":[{"id":"read-grid","type":"desktop_ui_grid_read","windowTitle":"Acceptance Editor","automationId":"orders","controlType":"DataGrid","result":"rows","metadataResult":"gridMetadata","maxRows":100,"maxColumns":30,"maxOutputChars":50000}]}
        valid_grid=call({"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{grid_workflow["name"]:grid_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_grid.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected a bounded UIA grid workflow: {valid_grid}")
        selection_workflow={**main_workflow,"name":"UI multi selection acceptance","activities":[{"id":"select-many","type":"desktop_ui_select_many","windowTitle":"Acceptance Editor","automationId":"queue","controlType":"List","values":["Ready","Queued"],"mode":"replace","result":"selectedItems"}]}
        valid_selection=call({"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{selection_workflow["name"]:selection_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_selection.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected bounded native list selection: {valid_selection}")
        browser_selection_workflow={**main_workflow,"name":"Browser multi selection acceptance","activities":[{"id":"select-many","type":"browser_select_many","selectorKind":"role","selector":"listbox:Categories","values":["books","music"],"result":"selectedValues"}]}
        valid_browser_selection=call({"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{browser_selection_workflow["name"]:browser_selection_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_browser_selection.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected a native browser multi-selection workflow: {valid_browser_selection}")
        healing_workflow={**main_workflow,"name":"Browser selector recovery acceptance","activities":[{"id":"save","type":"browser_click","selectorKind":"role","selector":"button:Save order","selectorHealing":"accessible_role"}]}
        valid_healing=call({"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{healing_workflow["name"]:healing_workflow}}}}).get("result",{}).get("structuredContent",{})
        if not valid_healing.get("valid"):
            raise RuntimeError(f"Frozen MCP rejected opt-in same-role selector recovery: {valid_healing}")
        invalid_healing={**healing_workflow,"activities":[{**healing_workflow["activities"][0],"selectorKind":"css","selector":"button.save"}]}
        rejected_healing=call({"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"openrpa_validate_workflow_drafts","arguments":{"workflows":{invalid_healing["name"]:invalid_healing}}}}).get("result",{}).get("structuredContent",{})
        if rejected_healing.get("valid") or "browser-selector-healing-scope" not in {item.get("code") for item in rejected_healing.get("problems",[])}:
            raise RuntimeError(f"Frozen MCP did not reject selector recovery on CSS selectors: {rejected_healing}")
        invalid_keys = {**key_workflow, "activities": [{**key_workflow["activities"][0], "key": "Alt+F4"}]}
        rejected_keys = call({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "openrpa_validate_workflow_drafts",
                       "arguments": {"workflows": {invalid_keys["name"]: invalid_keys}}},
        }).get("result", {}).get("structuredContent", {})
        if rejected_keys.get("valid") or "desktop-uia-key" not in {
            problem.get("code") for problem in rejected_keys.get("problems", [])
        }:
            raise RuntimeError(f"Frozen MCP did not reject the blocked desktop shortcut: {rejected_keys}")

        request = {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "openrpa_stage_workflow_draft", "arguments": {"name": draft["name"], "workflow": draft}},
        }
        response = call(request)
        result = response.get("result", {}).get("structuredContent", {})
        if not result.get("staged"):
            raise RuntimeError(f"Frozen MCP stage call failed: {response}")
        staged_path = root / ".openrpa" / "mcp-live-draft.json"
        staged = json.loads(staged_path.read_text(encoding="utf-8"))
        if staged.get("status") != "building" or staged.get("workflow") != draft:
            raise RuntimeError(f"Frozen bridge wrote an invalid live snapshot: {staged}")
        print(f"PASS: frozen MCP advertises {len(expected_inspection_tools)} desktop inspection tools, hides live browser/desktop actions without grants, exposes {len(expected_live_browser_tools)} browser actions and desktop actions {sorted(desktop_operations)} with opt-ins, bounds process arguments and multi-selection names, blocks loopback navigation; bounded JSON API mapping and value-free schema discovery accepted; malformed pointers/result collisions and schema-output collisions rejected; selector recovery is advertised off by default, accepted for exact role selectors and rejected for CSS; desktop_ui_press accepted Enter and rejected Alt+F4; multi-selection workflow validated; staged {result['activityCount']} activity; status=building; digest={staged['draftId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
