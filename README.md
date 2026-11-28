# CasaMemo Media Tools

Build and verify the Media Tools used by CasaMemo. FFmpeg and FFprobe are built from the same FFmpeg source. The macOS ExifTool payload retains the official standalone source distribution and uses macOS's system Perl. The Windows candidate builds ExifTool against CasaMemo's security-patched native UCRT64 Perl.

## Build and validate

Use a worktree path without spaces. Install Python 3.9+, Bash, curl, make, patch, Meson, Ninja and pkgconf in your build environment. NASM enables x64 SIMD. A Git checkout needs Git for the archive inventory check. macOS requires Xcode or the Command Line Tools. Windows requires an MSYS2 UCRT64 shell with Python 3.14 or later for Zstandard archives, plus the Git, GCC, CMake, Meson, Ninja, NASM and pkgconf packages listed in the [CI workflow](.github/workflows/build.yml).

```sh
python3 -m unittest discover -s tests
bash scripts/build.sh macos-arm64
python3 tests/runtime.py dist/macos-arm64
```

Use `macos-x64` for an Intel build or a cross-build on Apple silicon. Use `windows-x64` in UCRT64 and set `PYTHON=python` if needed. `--architecture-only` validates a package without executing it. Record Rosetta runs as translated evidence and run the Intel package on an Intel host before release.

In UCRT64, run `PYTHON=python bash scripts/build.sh windows-x64` and then
`python tests/runtime.py dist/windows-x64`. The build checks the installed MSYS2
runtime revisions against their source pins and records the selected linker
objects. The same build applies the pinned security patches to the verified
MSYS2 Perl recipe and compiles Perl, core XS, the ExifTool launcher and the
external extensions in a workspace-local directory. It runs focused Perl
regex tests and records the built DLL identities, loaded library versions and
per-binary linker inputs. The Windows ZIP includes the launcher, runtime DLLs
and selected modules, with no end-user Perl or MSYS2 installation required.

Source downloads are cached in `build/downloads`. Set `MEDIA_SOURCE_CACHE` to reuse an external verified cache. Every build rechecks hashes and uses a fresh build directory. `JOBS` controls parallel work. `REVISION` defaults to `r1`. The build refuses an existing destination under `dist`. Use a fresh output directory or move a prior candidate out of that location before rebuilding.

The FFmpeg build enables raw H.264 and HEVC demuxing. A small source patch keeps
the initial probe buffer when the caller requests a zero input offset for these
two elementary stream formats. The source companion includes the patch.

## Packages

| Artifact | Contents |
| --- | --- |
| `casamemo-ffmpeg-9.1-<platform>-r1.zip` | FFmpeg under `bin/`, build records and licence notices. The Windows ZIP also contains FFprobe. |
| `casamemo-ffprobe-9.1-<macos-platform>-r1.zip` | FFprobe under `bin/`, with the matching FFmpeg version, records and notices |
| `casamemo-exiftool-13.64-<macos-platform>-r1.tar.gz` | The byte-identical upstream ExifTool source distribution, including its `lib/` tree and licence |
| `casamemo-exiftool-13.64-windows-x64-r1.zip` | `exiftool.exe` with sibling `exiftool_files/`, runtime inventory, PE imports and licence notices |
| `casamemo-sources-<platform>-r1.zip` | Pinned source archives, build records, licence texts and the build recipe |
| `artifacts.json` and `SHA256SUMS` | Artifact hashes, sizes, package roles and provisioning information |

CasaMemo schema v1 requires separate matching FFmpeg and FFprobe entries on macOS. Both entries use ZIP archive hashes and the ExifTool entry uses its TAR.GZ archive hash. The Windows FFmpeg ZIP contains both executables and uses a null `ffprobe` entry. The Windows ExifTool entry uses its ZIP hash. These candidate indexes supply metadata for a later manifest update.

CI builds and tests all three target architectures and uploads macOS candidates. Windows binary uploads and finalization remain blocked pending independent source and security acceptance and Windows 10 x64 native provisioning QA. Read the [security record](docs/SECURITY.md), [licensing inventory](THIRD_PARTY_NOTICES.md) and [owner release checklist](docs/RELEASING.md) before distributing them.
