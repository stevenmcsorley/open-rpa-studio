# Product evidence and independent implementation notes

## Scope

No UiPath binary or licensed installation was present in the inspected local application locations, and no target was opened in REA. Therefore no claim about UiPath implementation internals or runtime behavior is made. REA remains available for future evidence gathering against a lawfully supplied, authorised target; it is not the code-generation engine.

This implementation is independently authored from public product documentation. It does not include proprietary source, assets, binaries, or vendor workflow formats.

## Publicly documented observations

| Capability | Documented behavior relevant to this implementation | Source |
|---|---|---|
| Studio authoring interface | Activities are composed in a designer; projects include variables, panels and package/dependency workflows. | [UiPath Studio user interface](https://docs.uipath.com/studio/standalone/latest/user-guide/the-user-interface) |
| Debugging | Studio documents breakpoints, local values, variables and arguments during debugging. | [About debugging](https://docs.uipath.com/studio/standalone/latest/user-guide/about-debugging) |
| Workflow data | Variables represent values within a workflow; arguments pass values between workflows with direction and type. | [Managing arguments](https://docs.uipath.com/studio/standalone/latest/user-guide/managing-arguments) |
| Control flow | State machines model states, final states, triggers and transitions. | [State machines](https://docs.uipath.com/studio/standalone/latest/user-guide/state-machines) |
| Project manifest | Project configuration records workflow entry point, dependencies, and project metadata. | [Project.json](https://docs.uipath.com/studio/standalone/latest/user-guide/about-the-projectjson-file) |
| Dependencies | Project dependencies are managed with package/version information. | [Managing dependencies](https://docs.uipath.com/studio/standalone/latest/user-guide/managing-dependencies) |
| Publishing | Projects can be packaged and published to configured feeds. | [Publishing projects](https://docs.uipath.com/studio/standalone/latest/user-guide/about-publishing-automation-projects) |
| Security | Documentation advises against hard-coding credentials in workflows and describes secure credential handling. | [Project organization and exception handling](https://docs.uipath.com/studio/standalone/latest/user-guide/project-organization) |

These sources establish product concepts, not exact UI parity or undocumented semantics. Our workflow format and activity behavior are independent choices. Runtime parity, selector behavior, recorder output and package compatibility remain unverified.

## Verification

Each implemented feature is tested against this project's own documented format and behavior. No feature is marked compatible with UiPath solely because it has a similar label.
