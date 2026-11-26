# CasaMemo Media Tools repository rules

This repository builds and inspects the FFmpeg, FFprobe and ExifTool distributions for CasaMemo. Keep application implementation, provisioning manifests, credentials, signing material and private media outside it.

- Follow the owner's exact worktree, branch and base. Preserve existing changes and staging. Keep implementation changes uncommitted. The owner performs Git history and remote mutations, PR and CI operations, signing, notarization, publication and deployment.
- Treat upstream releases, advisories and application references as read-only evidence. Pin every media source archive and verify its hash before extraction or use. Review fix provenance and transitive dependencies when changing a pin.
- Build FFmpeg and FFprobe together with the LGPL 2.1-or-later configuration. Keep GPL, non-free, version-3, auto-detected dependencies and networking disabled. Justify changes to the capability allowlist against CasaMemo's workflows.
- Preserve provisioning layout, piped output and local-file processing, the three supported architectures and macOS 13. Preserve Windows 10 x64 compatibility. Use synthetic or documented redistributable fixtures.
- Keep complete notices, corresponding sources, patch/build records, architecture and linkage evidence together. Application and upstream licence terms apply independently.
- Run focused archive tests and native capability tests. Label cross-compilation, translated execution and target-native runtime evidence accurately.
- Treat CI outputs as candidates. Version published assets immutably. Release eligibility depends on reviewed security and source provenance, complete licensing and native QA. Follow [the owner release checklist](docs/RELEASING.md).
