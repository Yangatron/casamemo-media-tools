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
| ExifTool geolocation database | Bundled with 13.64 | Based on the [GeoNames gazetteer data](https://www.geonames.org/export/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Phil Harvey filters and reformats the data for ExifTool. CasaMemo redistributes the resulting `Geolocation.dat` unmodified. [ExifTool database documentation](https://exiftool.org/geolocation.html). |
| CasaMemo native Perl runtime | 5.44.0, UCRT64 r1 | Perl 5.44.0 under its Artistic License or GPL terms. The source companion retains the exact MSYS2 5.44.0-3 recipe, Perl archive and ordered security patches. The Windows ExifTool ZIP carries embedded bzip2 1.0.8 and supplemental notices at `licenses/perl/Third-Party.txt`. |
| Windows Perl XS modules | IO::Compress::Brotli 0.023, Win32::FindFile 0.15, Win32::API 0.84, Compress::Raw::Zlib 2.222 | Perl terms. Brotli 1.2.1 uses the MIT License and zlib 1.4 uses the zlib licence. The package carries the module and embedded component notices. |
| MSYS2 Windows runtime objects in FFmpeg and FFprobe | GCC 16.2.0-7, MinGW-w64 14.0.0.r598.ge3d18511f-1, default manifest 20260815-1 | GCC Runtime Library Exception where applicable, MinGW-w64 CRT terms, winpthreads copyright and permission notices, and public domain default manifest. The source companion includes the pinned MSYS2 source packages and linker object inventory. |
| MSYS2 GCC DLLs in Windows ExifTool | 16.2.0-7 | Separately shipped `libgcc_s_seh-1.dll` and `libstdc++-6.dll` retain their GPLv3 terms and GCC Runtime Library Exception. The source companion retains their matching MSYS2 recipe and sources. The exception covers eligible compiled combinations with independent modules. [FSF exception guidance](https://www.gnu.org/licenses/gcc-exception-3.1-faq.html). |
| MSYS2 MinGW-w64 CRT and winpthreads in Windows ExifTool | 14.0.0.r598.ge3d18511f-1 | The runtime and source companion include the MinGW-w64 CRT and winpthreads notices. The Windows archive includes the pinned `libwinpthread-1.dll`. |

The FFmpeg build links its source-built libraries statically. Distribute the matching source asset alongside each runtime, with any patches and the exact build instructions. Preserve recipients' rights to modify, relink or rebuild as applicable, and review CasaMemo distribution terms for compatibility. Retain immutable corresponding source for each public runtime revision. The owner must assess codec patents and licence terms before release.
