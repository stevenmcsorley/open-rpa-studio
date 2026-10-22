import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openrpa.component_package import install_component, pack_component
from openrpa.model import WorkflowError, load_project


def workflow(name, activities=None):
    return {"format": "openrpa.workflow", "formatVersion": 1, "name": name,
            "executionModel": "sequence", "variables": [], "arguments": [],
            "activities": activities or []}


def make_project(root: Path, workflows: dict[str, dict], main="Main"):
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for index, (name, value) in enumerate(workflows.items()):
        relative = f"workflows/{index}.workflow.json"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = relative
    (root / "project.json").write_text(json.dumps({"format": "openrpa.project", "formatVersion": 1,
        "name": root.name, "main": main, "workflows": paths}), encoding="utf-8")


class ComponentPackageTests(unittest.TestCase):
    def test_round_trip_exports_dependency_closure_deterministically_and_installs_namespaced_workflows(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            make_project(source, {
                "Main": workflow("Main"),
                "Prepare": workflow("Prepare", [{"id": "log", "type": "log", "message": "prepared"}]),
                "Daily Report": workflow("Daily Report", [{"id": "call", "type": "invoke_workflow", "workflow": "Prepare", "inputs": {}}]),
                "Unused": workflow("Unused"),
            })
            first = base / "one.orwc"
            second = base / "two.orwc"
            result = pack_component(source, "Daily Report", first)
            pack_component(source, "Daily Report", second)
            self.assertEqual(result["workflowCount"], 2)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            make_project(target, {"Main": workflow("Main")})
            installed = install_component(first, target, "Acme Ops")
            self.assertEqual(installed["entryWorkflow"], "Acme Ops / Daily Report")
            project, root = load_project(target)
            self.assertIn("Acme Ops / Prepare", project["workflows"])
            self.assertIn("Acme Ops / Daily Report", project["workflows"])
            entry = json.loads((root / project["workflows"][installed["entryWorkflow"]]).read_text(encoding="utf-8"))
            self.assertEqual(entry["activities"][0]["workflow"], "Acme Ops / Prepare")
            self.assertEqual(project["main"], "Main")
            with self.assertRaises(WorkflowError) as conflict:
                install_component(first, target, "Acme Ops")
            self.assertEqual(conflict.exception.code, "component-conflict")

    def test_rejects_unsafe_archive_paths_before_writing_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            make_project(target, {"Main": workflow("Main")})
            malicious = base / "bad.orwc"
            member = json.dumps(workflow("Bad")).encode()
            manifest = {"format": "org.openrpa.component", "formatVersion": 1,
                "name": "Bad", "entryWorkflow": "Bad", "workflows": [{"name": "Bad",
                "path": "workflows/../escape.workflow.json", "size": len(member),
                "sha256": "0" * 64}]}
            with zipfile.ZipFile(malicious, "w") as archive:
                archive.writestr("component-manifest.json", json.dumps(manifest))
                archive.writestr("workflows/../escape.workflow.json", member)
            with self.assertRaises(WorkflowError) as error:
                install_component(malicious, target, "Untrusted")
            self.assertEqual(error.exception.code, "component-path")
            project, _ = load_project(target)
            self.assertEqual(set(project["workflows"]), {"Main"})

    def test_rejects_component_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            make_project(source, {"Main": workflow("Main")})
            make_project(target, {"Main": workflow("Main")})
            package = base / "main.orwc"
            pack_component(source, "Main", package)
            with zipfile.ZipFile(package) as original:
                manifest = json.loads(original.read("component-manifest.json"))
                payload = original.read(manifest["workflows"][0]["path"]) + b" "
            manifest["workflows"][0]["size"] = len(payload)
            with zipfile.ZipFile(package, "w") as changed:
                changed.writestr("component-manifest.json", json.dumps(manifest))
                changed.writestr(manifest["workflows"][0]["path"], payload)
            with self.assertRaises(WorkflowError) as error:
                install_component(package, target, "Untrusted")
            self.assertEqual(error.exception.code, "component-integrity")


if __name__ == "__main__":
    unittest.main()
