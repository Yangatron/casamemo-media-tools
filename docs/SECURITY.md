# Media Tools security and provenance

Review upstream advisories and the exact code/configuration before updating any pin or making a release. Recheck affected versions, enabled components and reachability. Record fix commits or source comparisons and use benign fixtures for capabilities. Archive URLs and SHA-256 pins live in `sources.json`. Verify release signatures and publisher hashes when available. Retain source, patches, configuration and notices with the candidate.

## FFmpeg

The downloaded FFmpeg 9.1 release passed verification of its detached OpenPGP signature against the
[upstream published fingerprint](https://ffmpeg.org/download.html#releases)
`FCF986EA15E6E293A5644F10B4322F04D67658D8`. The dav1d archive also matched the
[VideoLAN publisher SHA-256](https://downloads.videolan.org/pub/videolan/dav1d/1.5.5/dav1d-1.5.5.tar.xz.sha256).

The 9.1 release source contains the TIFF Deflate length check for CVE-2026-70631 and the native WebP alpha length check for CVE-2026-125098. It also contains the EXIF parsing budget for CVE-2026-125180. Review used [FFmpeg security records](https://ffmpeg.org/security.html), the [WebP fix](https://github.com/FFmpeg/FFmpeg/commit/92b318e0b33623720d9f128ad7bc5fa8277c34f7) and [EXIF fix](https://github.com/FFmpeg/FFmpeg/commit/30fff47764e59f02ac7868bb832ed51a88f949fd). The pinned libwebp source postdates its [CVE-2023-4863 fix](https://github.com/webmproject/libwebp/releases/tag/v1.3.2). zlib 1.4 contains the upstream [November 2026 fixes](https://github.com/madler/zlib/releases/tag/v1.4).

The FFmpeg CLI keeps only file and pipe protocols. Its enabled demuxers exclude playlists and network-based input. The application remains responsible for safe input paths, time and resource bounds and safe process invocation. Run all release checks against the files that will actually be distributed.

## Windows ExifTool

The official ExifTool 13.64 x64 ZIP is authentic by the [published hash](https://sourceforge.net/projects/exiftool/files/) and extracts successfully. The payload includes Strawberry Perl 5.32.1.1 and a static Brotli 1.0.4 inside IO::Compress::Brotli 0.004001. Compared with the verified Strawberry Perl distribution, the Windows launcher, Brotli XS and Win32::FindFile XS are additional native builds. Corresponding source for a module version alone cannot show the exact inputs and patches used by those DLLs.

ExifTool uses Brotli to read compressed EXIF and XMP metadata in JPEG XL. The bundled decoder predates the [fix for CVE-2020-8927](https://github.com/google/brotli/releases/tag/v1.0.9). The affected Windows distribution is excluded from release eligibility. A replacement must retain JPEG XL metadata support and pass the native validation below. The maintained [Brotli 1.2.1 release](https://github.com/google/brotli/releases/tag/v1.2.1) also fixes CVE-2026-111497.

A source-verifiable replacement is available for the Brotli component. [IO::Compress::Brotli 0.023](https://metacpan.org/release/TIMLEGGE/IO-Compress-Brotli-0.023) embeds Brotli 1.2.1 and retains the two-argument decoder API ExifTool uses. The source archive matched CPAN’s SHA-256 `fb30386115589dbdc71ff3ab0af1b67c33c202df4bbdb4e00093f1c50a2cf2f8`. A candidate assembly can reuse the [maintained Strawberry Perl 5.42.3.1 x64 portable runtime](https://strawberryperl.com/), the official ExifTool source, the [CC0 launcher source](https://oliverbetz.de/pages/Artikel/Portable-Perl-Applications), and the source of any needed XS libraries, including [Win32::FindFile](https://metacpan.org/release/GRIAN/Win32-FindFile-0.15). Compile only the XS extensions and launcher against the selected portable Perl toolchain. Verify the ABI, preserve Unicode paths, keep all DLLs and notices required at runtime, identify each linked component and retain matching source and build instructions. Select the minimal runtime with an auditable inventory rather than distributing a full Perl development kit.

No tested Windows assembly with this closure is pinned or generated here. Keep the official 13.64 Windows ZIP and unverified substitutes out of CI distribution and public releases. Native acceptance must include JPEG XL Brotli EXIF and XMP extraction, ordinary metadata, Unicode paths, original integrity, full PE dependency closure and the existing sibling `exiftool_files` layout on the Windows baseline. Upstream labels the pinned macOS source version 13.64 a development release. Retain its stock macOS functionality via the upstream Perl archive and OS Perl. Windows bundled Brotli functionality must be preserved in the future candidate.
