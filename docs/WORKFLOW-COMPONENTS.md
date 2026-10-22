# Reusable workflow components

Open RPA Studio can package a workflow and its statically invoked child workflows as a deterministic `.orwc` component. Components are built only from the native versioned workflow format; installing one does not install Python packages, native binaries, or third-party executable code.

## Export a component

Choose an entry workflow from a saved, valid project. In **Workflow Manager**, select **Export component** for the currently active workflow. The exporter follows literal `Invoke Workflow` references recursively, includes that dependency closure, and omits unrelated project workflows and project files. The CLI can do the same:

```powershell
uv run openrpa component-pack .\my-project Main .\customer-import.orwc
```

The command prints the entry workflow, dependency count, and SHA-256 of the archive. The archive is deterministic for unchanged workflow content.

## Install into a project

In **Workflow Manager**, choose **Install component** and select the `.orwc` file. Studio asks for a namespace to keep imported workflow names distinct. Imported workflows are added as ordinary editable project workflows; references among the component workflows are rewritten to the namespaced versions. The project's current main workflow is unchanged. The CLI can do the same:

```powershell
uv run openrpa component-install .\customer-import.orwc .\my-project CustomerImport
uv run openrpa validate .\my-project
```

The workflow manager can then open the imported workflows, or another workflow can invoke the component entry workflow using the regular `Invoke Workflow` activity.

## Safety and current scope

Installation validates archive paths, entry counts, expanded size, workflow sizes, SHA-256 file digests, component format version, all workflow schemas, and invocation references before publishing the updated project manifest. Workflows are written under `workflows/components/`; the manifest is atomically replaced last. Namespace conflicts fail without replacing existing workflows. A failed install removes only the new component directory.

The SHA-256 digest detects accidental modification and binds the displayed result to the package bytes; it does **not** establish who published the package. Components are not signed. Inspect workflows from untrusted sources before executing them. They use the normal static run-impact review, permission grants, runtime quotas, and audit history.

This is a declarative reusable-workflow component format, not yet an arbitrary native plug-in API. It does not load executable extensions, add new activity types, resolve third-party dependencies, or provide a public registry. The format is versioned so a later signed extension system can build on validated package distribution without making untrusted code part of this first step.
