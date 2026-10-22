# Platform releases

Open RPA Studio publishes platform-specific packages on each versioned GitHub release. Packages include the matching native Open RPA MCP bridge for that operating system and CPU architecture.

| Platform | Package | Architecture |
|---|---|---|
| Windows | NSIS `.exe` installer | x64 |
| Linux | `.deb` and `.AppImage` | x64 |
| macOS | `.dmg` disk image | Apple Silicon (arm64) and Intel (x86_64) |

Linux packages are built on Ubuntu 22.04, which supplies Tauri's required WebKitGTK 4.1 development libraries. Debian-based systems must have the Tauri WebKitGTK runtime dependencies installed; AppImage does not bundle WebKitGTK. See the [Tauri Linux prerequisites](https://v2.tauri.app/start/prerequisites/#linux) for the package list.

The macOS disk images are currently unsigned and not notarized. They can be built without Apple Developer credentials, but Gatekeeper may block first launch until the user approves the downloaded app in macOS privacy settings. Do not bypass organization security policy to launch an unsigned build.

The v0.1.128 release includes a Windows x64 installer, Linux x64 `.deb` and `.AppImage` packages, and separate Apple Silicon (`arm64`) and Intel (`x86_64`) macOS `.dmg` files. Each package includes the matching native MCP bridge. SHA-256 checksum files are attached alongside the installers.

The release workflow builds Linux and both macOS architectures on native GitHub-hosted runners, smoke-checks the packaged bridge, and uploads the packages and SHA-256 files to the existing version tag. A workflow dispatch can add these assets to a release created before the cross-platform workflow was introduced.
