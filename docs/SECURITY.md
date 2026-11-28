# Media Tools security and provenance

Review upstream advisories and the exact code/configuration before updating any pin or making a release. Recheck affected versions, enabled components and reachability. Record fix commits or source comparisons and use benign fixtures for capabilities. Archive URLs and SHA-256 pins live in `sources.json`. Verify release signatures and publisher hashes when available. Retain source, patches, configuration and notices with the candidate.

## FFmpeg

The downloaded FFmpeg 9.1 release passed verification of its detached OpenPGP signature against the
[upstream published fingerprint](https://ffmpeg.org/download.html#releases)
`FCF986EA15E6E293A5644F10B4322F04D67658D8`. The dav1d archive also matched the
[VideoLAN publisher SHA-256](https://downloads.videolan.org/pub/videolan/dav1d/1.5.5/dav1d-1.5.5.tar.xz.sha256).

The 9.1 release source contains the TIFF Deflate length check for CVE-2026-70631 and the native WebP alpha length check for CVE-2026-125098. It also contains the EXIF parsing budget for CVE-2026-125180. Review used [FFmpeg security records](https://ffmpeg.org/security.html), the [WebP fix](https://github.com/FFmpeg/FFmpeg/commit/92b318e0b33623720d9f128ad7bc5fa8277c34f7) and [EXIF fix](https://github.com/FFmpeg/FFmpeg/commit/30fff47764e59f02ac7868bb832ed51a88f949fd). The pinned libwebp source postdates its [CVE-2023-4863 fix](https://github.com/webmproject/libwebp/releases/tag/v1.3.2). zlib 1.4 contains the upstream [November 2026 fixes](https://github.com/madler/zlib/releases/tag/v1.4).

The FFmpeg CLI keeps only file and pipe protocols. Its enabled demuxers exclude playlists and network-based input. The application remains responsible for safe input paths, time and resource bounds and safe process invocation. Run all release checks against the files that will actually be distributed.

## Windows FFmpeg and FFprobe redistribution

The native build checks MSYS2 GCC 16.2.0-7, MinGW-w64 CRT and winpthreads
14.0.0.r598.ge3d18511f-1, and the Windows default manifest revision 20260815-1.
It records the selected archive members and startup objects from both GNU
linker maps, with their MSYS2 package owners. The source companion includes
the hash-verified MSYS2 source packages and their exact recipes and patches.
The CRT and winpthreads source packages carry the MinGW-w64 Git source
selected by both recipes at `e3d18511f9759d455cae20c34703eea4a0723cf3`.
The PE import checks cover Windows and UCRT imports.

The [GCC Runtime Library Exception](https://www.gnu.org/licenses/gcc-exception-3.1.html)
applies to files that carry the exception and to eligible compilation processes.
The [MinGW-w64 CRT package](https://packages.msys2.org/base/mingw-w64-crt) lists
ZPL-2.1. The [winpthreads notice](https://github.com/mingw-w64/mingw-w64/blob/master/mingw-w64-libraries/winpthreads/COPYING)
contains the required copyright and permission notices. The archive carries
these notices with the GCC and MinGW-w64 texts and build metadata. The source
pin for the default manifest retains its public-domain generator. Windows
binary uploads and finalization remain blocked under the ExifTool gate below.

## Windows ExifTool

The native Windows build keeps ExifTool 13.64 and builds its Perl runtime and
XS modules with the pinned Windows UCRT64 toolchain. The vendor Windows ExifTool
package is excluded. The runtime uses the existing `exiftool.exe` and sibling
`exiftool_files` layout. The launcher passes UTF-8 arguments, clears external
Perl options and restricts native DLL resolution to the runtime and Windows
system directories. Windows added the launcher’s UTF-8 manifest setting in
version 1903. [Microsoft manifest documentation](https://learn.microsoft.com/en-us/windows/win32/sbscs/application-manifests#activecodepage).

### Patched Perl

The source lock records the MSYS2 UCRT64 Perl 5.44.0-3 source package and its
nested upstream archive. The downloaded reference binary passed the MSYS2
signature and publisher SHA-256 checks. Its `.BUILDINFO` recipe SHA-256
matches the retained source package’s `PKGBUILD`
(`93f5177bced5251845ea535fadaaceebc0fd49d9ab967880fd228934ca3321b0`).
MSYS2’s published binary remains affected by CVE-2026-15534. The build uses
the verified recipe’s Windows preparation and compilation commands. Between
those steps it applies upstream `568e6fd` followed by `54cf3d4`.
The main fix’s parent is the prerequisite. The Perl v5.44.0 tag already
contains the CVE-2026-19487 fix. [MSYS2 package](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-perl),
[MSYS2 security tracker](https://packages.msys2.org/security),
[prerequisite](https://github.com/Perl/perl5/commit/568e6fd238867bb9e99fa3f47cba3169009239e0),
[main fix](https://github.com/Perl/perl5/commit/54cf3d44cbbedd17d774e9a37921963e8fd5d0cb),
[CVE-2026-19487 fix](https://github.com/Perl/perl5/commit/1a21abacaf6f684928bae8baaa153733c8c238eb).

The custom build identifies itself as `CasaMemo MSYS2 UCRT64 r1 (CVE-2026-15534)`
and compiles its own Perl DLL, headers and core XS. The build records the
applied patch hashes and the loaded interpreter identity. It checks that the
Perl DLL’s link map includes the patched regex translation unit and runs
focused upstream regex tests. The Win32::API source came from the exact MSYS2
0.84-12 source package. Its recipe also matches the signed MSYS2 binary’s
`.BUILDINFO` digest
(`82d5aacd0ac3a212ad5173c8c5965a9fa14eeee91e7eb77be6e0908e2b98c4c1`).
The Win32::API binary and other external XS modules are built locally against
the patched Perl. The loaded Brotli encoder and decoder must report 1.2.1,
and loaded zlib must report 1.4. Brotli 1.2.1 retains ExifTool's two-argument
decoder API and includes the fix for CVE-2026-111497. The rebuilt
Compress::Raw::Zlib extension uses the same zlib 1.4 source as FFmpeg.
[Win32::API package](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-perl-win32-api),
[Brotli 1.2.1 release](https://github.com/google/brotli/releases/tag/v1.2.1),
[zlib 1.4 release](https://github.com/madler/zlib/releases/tag/v1.4).

### Native sources and notices

The Windows source companion retains the exact MSYS2 Perl and Win32::API
source packages with their recipes and patches, both Perl security patches,
the locally built extension sources, and the CasaMemo build instructions.
It includes the MSYS2 recipe repository's BSD 3-Clause licence.
[MSYS2 recipe licence](https://github.com/msys2/MINGW-packages/blob/b8dd0203a9a696cee154113c0c5671187dc37063/LICENSE).
It retains the exact MSYS2 GCC, MinGW-w64 CRT and winpthreads source packages.
The shipped GCC and winpthreads DLLs are extracted from pinned, signature-
verified UCRT64 packages whose `.BUILDINFO` recipe hashes match the retained
source recipes. Each candidate records their package owners and SHA-256
values, the PE import closure, and the compiler and runtime files selected
by the linker for each locally built native runtime binary.
The local link inventory also records the Perl import archive, the static
Win32CORE archive in the Perl DLL, and the Brotli archive in its XS DLL.

The separately shipped `libgcc_s_seh-1.dll` and `libstdc++-6.dll` require
GCC licence and exception notices and equivalent access to corresponding
source under GPLv3 §6. The Runtime Library Exception permits eligible
compiled combinations under terms consistent with the independent modules’
licences. The package includes MinGW-w64 CRT and winpthreads notices and
the supplemental Perl, bzip2 and GeoNames notices. [FSF exception guidance](https://www.gnu.org/licenses/gcc-exception-3.1-faq.html),
[GPLv3 §6](https://www.gnu.org/licenses/gpl-3.0.html#section6),
[third-party notices](../THIRD_PARTY_NOTICES.md).

Windows uploads and owner finalization remain blocked pending independent
security and source acceptance and native Windows 10 x64 provisioning QA.
