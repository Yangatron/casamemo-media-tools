# Third-party notices

MIT applies to the independently authored repository material. Upstream programs and components retain the terms identified below and in their source archives. The Server Side Up repository was used as an architectural reference. The build scripts here are independently authored.

| Included component | Version | Licence and purpose |
| --- | --- | --- |
| FFmpeg and FFprobe | 9.1 | LGPL 2.1 or later configuration. The two executables use their matching FFmpeg libraries and retain all upstream licence and credit material. The [raw zero-seek patch](patches/ffmpeg-9.1-raw-zero-seek.patch) is provided under the licence of the affected FFmpeg source. |
| libwebp and libsharpyuv | 1.6.0 | Upstream BSD terms and patent grant. WebP encoding and animation assembly. FFmpeg's native decoders read the output. |
| zlib | 1.4 | zlib licence. PNG and Deflate-compressed TIFF decoding and encoding support. |
| Little CMS | 2.20 | MIT. ICC profile detection and generation. |
| dav1d | 1.5.5 | BSD 2-Clause. Software AV1 decoding for AVIF and video. |
| ExifTool for macOS | 13.64 | Distributed under Perl's Artistic License option. Copyright 2003–2026 Phil Harvey. The original archive ships the upstream notice in README and the complete module source. The source companion includes the [Perl Artistic License text](licenses/ExifTool-Artistic.txt) from [Perl v5.42.3](https://github.com/Perl/perl5/blob/v5.42.3/Artistic). macOS provides the Perl interpreter and its OS modules. |
| Windows ExifTool source | 13.64 | Perl Artistic License option. The Windows candidate uses a separately compiled launcher with the pinned upstream scripts and modules. |
| Strawberry Perl runtime | 5.42.3.1 | Perl 5.42.3 under the upstream Artistic License or GPL terms. The source companion retains Perl source and Strawberry’s release recipe, including the core Compress::Raw::Bzip2 sources. The package carries the embedded bzip2 1.0.8 notice. |
| Windows Perl XS modules | IO::Compress::Brotli 0.023, Win32::FindFile 0.15, Win32::API 0.84, Compress::Raw::Zlib 2.222 | Perl terms. Brotli 1.2.1 uses the MIT License and zlib 1.4 uses the zlib licence. The package carries the module and embedded component notices. |
| MSYS2 Windows runtime objects in FFmpeg and FFprobe | GCC 16.2.0-7, MinGW-w64 14.0.0.r598.ge3d18511f-1, default manifest 20260815-1 | GCC Runtime Library Exception where applicable, MinGW-w64 CRT terms, winpthreads copyright and permission notices, and public domain default manifest. The source companion includes the pinned MSYS2 source packages and linker object inventory. |
| WinLibs runtime in Windows ExifTool | GCC 13.2.0, MinGW-w64 11.0.1 UCRT POSIX r8 | GCC runtime and MinGW-w64 notices from the matching upstream versions. Exact WinLibs downstream build inputs remain under review. |

The FFmpeg build links its source-built libraries statically. Distribute the matching source asset alongside each runtime, with any patches and the exact build instructions. Preserve recipients' rights to modify, relink or rebuild as applicable, and review CasaMemo distribution terms for compatibility. Retain immutable corresponding source for each public runtime revision. The owner must assess codec patents and licence terms before release.
