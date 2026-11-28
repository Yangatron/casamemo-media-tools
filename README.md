# CasaMemo Media Tools

Build and verify the Media Tools used by CasaMemo. FFmpeg and FFprobe are built from the same FFmpeg source. The macOS ExifTool payload retains the official standalone source distribution and uses macOS's system Perl. Windows ExifTool remains excluded from the package set pending [security and source verification](docs/SECURITY.md#windows-exiftool).

## Build and validate

Use a worktree path without spaces. Install Python 3.9+, Bash, curl, make, patch, Meson, Ninja and pkgconf in your build environment. NASM enables x64 SIMD. macOS requires Xcode or the Command Line Tools. Windows requires an MSYS2 UCRT64 shell with the GCC, Python, Meson, Ninja, NASM and pkgconf packages listed in the [CI workflow](.github/workflows/build.yml).

```sh
python3 -m unittest discover -s tests
bash scripts/build.sh macos-arm64
python3 tests/runtime.py dist/macos-arm64
```

Use `macos-x64` for an Intel build or a cross-build on Apple silicon. Use `windows-x64` in UCRT64 and set `PYTHON=python` if needed. `--architecture-only` validates a package without executing it. Record Rosetta runs as translated evidence and run the Intel package on an Intel host before release.

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
| `casamemo-sources-<platform>-r1.zip` | Pinned source archives, build records, licence texts and the build recipe |
| `artifacts.json` and `SHA256SUMS` | Artifact hashes, sizes, package roles and provisioning information |

CasaMemo schema v1 requires separate matching FFmpeg and FFprobe entries on macOS. Both entries use ZIP archive hashes and the ExifTool entry uses its TAR.GZ archive hash. The Windows FFmpeg ZIP contains both executables and uses a null `ffprobe` entry. These candidates supply metadata for the later manifest update. A complete Windows provisioning set still requires an eligible ExifTool ZIP.

CI builds and tests all three target architectures and uploads macOS candidates. Windows binary uploads remain withheld pending the linked runtime source and licence review. Read the [security record](docs/SECURITY.md), [licensing inventory](THIRD_PARTY_NOTICES.md) and [owner release checklist](docs/RELEASING.md) before distributing them.
