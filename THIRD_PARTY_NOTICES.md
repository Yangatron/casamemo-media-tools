# Third-party notices

MIT applies to the independently authored repository material. Upstream programs and components retain the terms identified below and in their source archives. The Server Side Up repository was used as an architectural reference. The build scripts here are independently authored.

| Included component | Version | Licence and purpose |
| --- | --- | --- |
| FFmpeg and FFprobe | 9.1 | LGPL 2.1 or later configuration. The two executables use their matching FFmpeg libraries and retain all upstream licence and credit material. |
| libwebp and libsharpyuv | 1.6.0 | Upstream BSD terms and patent grant. WebP encoding and animation assembly. FFmpeg's native decoders read the output. |
| zlib | 1.4 | zlib licence. PNG and Deflate-compressed TIFF decoding and encoding support. |
| Little CMS | 2.20 | MIT. ICC profile detection and generation. |
| dav1d | 1.5.5 | BSD 2-Clause. Software AV1 decoding for AVIF and video. |
| ExifTool for macOS | 13.64 | Distributed under Perl's Artistic License option. Copyright 2003–2026 Phil Harvey. The original archive ships the upstream notice in README and the complete module source. The source companion includes the [Perl Artistic License text](licenses/ExifTool-Artistic.txt) from [Perl v5.42.3](https://github.com/Perl/perl5/blob/v5.42.3/Artistic). macOS provides the Perl interpreter and its OS modules. |
| Windows GCC and MinGW-w64 runtime support | Recorded per build | GCC Runtime Library Exception where applicable, MinGW-w64 runtime terms and winpthreads notices. PE imports must resolve to Windows system components. Review the exact object and source obligations from the actual candidate before release. |

The FFmpeg build links its source-built libraries statically. Distribute the matching source asset alongside each runtime, with any patches and the exact build instructions. Preserve recipients' rights to modify, relink or rebuild as applicable, and review CasaMemo distribution terms for compatibility. Retain immutable corresponding source for each public runtime revision. The owner must assess codec patents and licence terms before release.
