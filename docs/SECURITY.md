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

The official ExifTool 13.64 x64 ZIP is authentic by the [published hash](https://sourceforge.net/projects/exiftool/files/) and extracts successfully. The payload includes Strawberry Perl 5.32.1.1 and a static Brotli 1.0.4 inside IO::Compress::Brotli 0.004001. Compared with the verified Strawberry Perl distribution, the Windows launcher, Brotli XS and Win32::FindFile XS are additional native builds. Corresponding source for a module version alone cannot show the exact inputs and patches used by those DLLs.

ExifTool uses Brotli to read compressed EXIF and XMP metadata in JPEG XL. The bundled decoder predates the [fix for CVE-2020-8927](https://github.com/google/brotli/releases/tag/v1.0.9). The affected Windows distribution is excluded from release eligibility. A replacement must retain JPEG XL metadata support and pass the native validation below. The maintained [Brotli 1.2.1 release](https://github.com/google/brotli/releases/tag/v1.2.1) also fixes CVE-2026-111497.

The candidate builds [IO::Compress::Brotli 0.023](https://metacpan.org/release/TIMLEGGE/IO-Compress-Brotli-0.023)
with its bundled Brotli 1.2.1 and retains the two-argument decoder API used by
ExifTool. It builds [Win32::FindFile 0.15](https://metacpan.org/release/GRIAN/Win32-FindFile-0.15)
with a compatibility change for the newer XS parser. It also builds
Compress::Raw::Zlib 2.222 with zlib 1.4 because Strawberry’s corresponding
extension uses zlib 1.3.2. The build verifies the loaded zlib version. The
[zlib 1.4 release notes](https://github.com/madler/zlib/releases/tag/v1.4)
document the security fixes. Strawberry supplies the core modules and Win32::API
0.84. The source companion includes the upstream Perl source, Strawberry build
recipe, CPAN module sources, launcher, compatibility change and notices.

The build checks Strawberry Perl 5.42.3.1 against the [publisher SHA-256](https://strawberryperl.com/releases.json)
in the source lock and verifies the threaded x64 Perl 5.42 ABI. The launcher
uses the sibling `exiftool_files` layout documented by
[Oliver Betz](https://oliverbetz.de/pages/Artikel/Portable-Perl-Applications).
It uses wide Windows arguments, UTF-8 filename handling and a restricted DLL
search rooted at the sibling runtime and Windows system directories. The
runtime excludes the development toolchain and records every packaged DLL
and its PE imports. The build records the toolchain objects linked into the
launcher and newly built extensions. The Windows runtime test uses both Brotli
metadata boxes from ExifTool’s JXL2 fixture, a Unicode install directory and
Unicode input paths. Windows added the launcher’s UTF-8 process manifest
setting in Windows 10 version 1903. [Microsoft application manifest documentation](https://learn.microsoft.com/en-us/windows/win32/sbscs/application-manifests#activecodepage)

Strawberry’s upstream recipe identifies [WinLibs GCC 13.2.0, MinGW-w64 11.0.1 UCRT POSIX r8](https://github.com/StrawberryPerl/build-extlibs/releases/tag/gcc13.2_ucrt_posix).
The candidate carries the upstream GCC and MinGW-w64 source and notices. The
[WinLibs r8 source reference](https://sourceforge.net/projects/winlibs-mingw/files/13.2.0posix-18.1.5-11.0.1-ucrt-r8/)
archive with SHA-256 `de5d70be55a69b0009e6d6a32fde22f7270468ffd4a205f18a19c4a3c1dc4fd1`
contains only its README. The exact downstream patches and build scripts for
the shipped libgcc, libstdc++ and libwinpthread DLLs and the WinLibs runtime
objects linked into the new extensions and launcher remain unverified.
Complete that source evidence before redistribution. Native Windows 10 x64
acceptance and independent review are also pending. The official 13.64 Windows
ZIP remains excluded. Upstream labels the unchanged macOS source version 13.64
a development release.
