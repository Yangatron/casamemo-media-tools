#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: bash scripts/build.sh {macos-arm64|macos-x64|windows-x64}" >&2
    exit 2
fi

platform=$1
root=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$root"
python=${PYTHON:-python3}
cache=${MEDIA_SOURCE_CACHE:-"$root/build/downloads"}
jobs=${JOBS:-4}
mkdir -p build
work=$(mktemp -d "$root/build/$platform.XXXXXXXX")
prefix="$work/prefix"
mkdir -p "$prefix/lib" "$prefix/include" "$work/source" "$work/ffmpeg" "$work/metadata"
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=1795132800
unset CPATH C_INCLUDE_PATH LIBRARY_PATH CFLAGS CPPFLAGS LDFLAGS PKG_CONFIG_PATH PKG_CONFIG_SYSROOT_DIR
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
export PKG_CONFIG=${PKG_CONFIG:-pkg-config}
export AR=ar
export RANLIB=ranlib
exe=
platform_flags=()
build_flags=()
cross_file=()

case "$platform" in
    macos-arm64|macos-x64)
        [[ $(uname -s) == Darwin ]]
        export MACOSX_DEPLOYMENT_TARGET=13.0
        architecture=arm64
        [[ "$platform" == macos-arm64 ]] || architecture=x86_64
        export CC=clang
        export CFLAGS="-O2 -arch $architecture -mmacosx-version-min=13.0"
        export LDFLAGS="-arch $architecture -mmacosx-version-min=13.0"
        platform_flags+=(--target-os=darwin --enable-pthreads)
        if [[ $(uname -m) != "$architecture" ]]; then
            platform_flags+=(--enable-cross-compile)
            build_flags+=(--host="$architecture-apple-darwin")
            cat > "$work/dav1d-cross.ini" <<CROSS
[binaries]
c = 'clang'
ar = 'ar'
strip = 'strip'

[host_machine]
system = 'darwin'
cpu_family = '$architecture'
cpu = '$architecture'
endian = 'little'

[built-in options]
c_args = ['-arch', '$architecture', '-mmacosx-version-min=13.0', '-ffile-prefix-map=$work=/build']
c_link_args = ['-arch', '$architecture', '-mmacosx-version-min=13.0']
CROSS
            cross_file=(--cross-file "$work/dav1d-cross.ini")
        fi
        ;;
    windows-x64)
        [[ ${MSYSTEM:-} == UCRT64 && $(uname -m) == x86_64 ]]
        architecture=x86_64
        exe=.exe
        export CC=gcc
        export CFLAGS="-O2 -D_WIN32_WINNT=0x0A00 -DWINVER=0x0A00"
        export LDFLAGS="-static"
        export PKG_CONFIG_LIBDIR
        PKG_CONFIG_LIBDIR=$(cygpath -m "$PKG_CONFIG_LIBDIR")
        platform_flags+=(--target-os=mingw32 --enable-w32threads)
        ;;
    *)
        echo "unknown platform: $platform" >&2
        exit 2
        ;;
esac

# Prefer upstream SIMD where its assembler is available. Keep the chosen mode in the build record.
ffmpeg_cflags=$CFLAGS
map_root=$work
if [[ "$platform" == windows-x64 ]]; then
    map_root=$(cygpath -m "$work")
fi
export CFLAGS="$CFLAGS -ffile-prefix-map=$map_root=/build"

assembly=enabled
if [[ "$architecture" == x86_64 ]] && ! command -v nasm >/dev/null; then
    assembly=disabled
    platform_flags+=(--disable-x86asm)
fi

"$python" "$root/scripts/inputs.py" "$cache" "$work/source" ffmpeg libwebp zlib lcms2 dav1d
ffmpeg=("$work"/source/ffmpeg-*)
webp=("$work"/source/libwebp-*)
zlib=("$work"/source/zlib-*)
lcms=("$work"/source/lcms2-*)
dav1d=("$work"/source/dav1d-*)

(
    cd "${zlib[0]}"
    if [[ "$platform" == windows-x64 ]]; then
        make -f win32/Makefile.gcc -j"$jobs" libz.a PREFIX= CFLAGS="$CFLAGS"
        cp libz.a "$prefix/lib/"
        cp zlib.h zconf.h "$prefix/include/"
    else
        ./configure --static --prefix="$prefix"
        make -j"$jobs"
        make install
    fi
)
(
    cd "${webp[0]}"
    ./configure ${build_flags[@]+"${build_flags[@]}"} --prefix="$prefix" --enable-static --disable-shared \
        --disable-gl --disable-sdl --disable-png --disable-jpeg --disable-tiff --disable-gif \
        --disable-wic --disable-libwebpdemux
    make -j"$jobs"
    make install
)
(
    cd "${lcms[0]}"
    CPPFLAGS="-I$prefix/include" LDFLAGS="$LDFLAGS -L$prefix/lib" \
    ./configure ${build_flags[@]+"${build_flags[@]}"} --prefix="$prefix" --libdir="$prefix/lib" \
        --enable-static --disable-shared --without-jpeg --without-tiff
    make -C src -j"$jobs"
    make -C src install
    make -C include install
    mkdir -p "$prefix/lib/pkgconfig"
    cp lcms2.pc "$prefix/lib/pkgconfig/"
)

meson setup "$work/dav1d" "${dav1d[0]}" ${cross_file[@]+"${cross_file[@]}"} --prefix "$prefix" --libdir lib \
    --buildtype release --wrap-mode nodownload --default-library static \
    -Denable_tools=false -Denable_tests=false "-Denable_asm=$([[ "$assembly" == enabled ]] && echo true || echo false)"
meson compile -C "$work/dav1d" -j "$jobs"
meson install -C "$work/dav1d" --no-rebuild

(
    cd "${ffmpeg[0]}"
    ./configure "${platform_flags[@]}" --arch="$architecture" --cc="$CC" \
        --extra-cflags="$ffmpeg_cflags -I../../prefix/include" --extra-ldflags="$LDFLAGS -L../../prefix/lib" \
        --pkg-config="$PKG_CONFIG" --pkg-config-flags=--static \
        --disable-gpl --disable-nonfree --disable-version3 --disable-autodetect \
        --enable-static --disable-shared --disable-network --disable-doc --disable-debug \
        --disable-ffplay --disable-avdevice --disable-everything \
        --enable-zlib --enable-lcms2 --enable-libwebp --enable-libdav1d \
        --enable-protocol=file,pipe \
        --enable-demuxer=mov,matroska,avi,mpegts,mpegps,mpegvideo,asf,flv,ogg,mxf,ivf,dv,apng,gif,image2,image2pipe,webp_anim,image_jpeg_pipe,image_png_pipe,image_tiff_pipe,image_webp_pipe \
        --enable-parser=aac,ac3,av1,h263,h264,hevc,mjpeg,mpeg4video,mpegaudio,mpegvideo,opus,vc1,vorbis,vp8,vp9 \
        --enable-decoder=hevc,h264,libdav1d,vp8,vp9,mpeg1video,mpeg2video,mpeg4,msmpeg4v1,msmpeg4v2,msmpeg4v3,h263,h263i,h263p,wmv1,wmv2,wmv3,vc1,mjpeg,mjpegb,prores,dnxhd,dvvideo,theora,flv,ffv1,huffyuv,rawvideo,webp,webp_anim,gif,png,apng,tiff \
        --enable-encoder=mjpeg,png,rawvideo,libwebp,libwebp_anim \
        --enable-muxer=image2,image2pipe,webp,rawvideo,null,framehash \
        --enable-filter=scale,format,crop,setsar,setparams,xstack,colorspace,transpose,hflip,vflip,iccgen,iccdetect,overlay,pad,split
    make -j"$jobs" "ffmpeg$exe" "ffprobe$exe"
    cp "ffmpeg$exe" "ffprobe$exe" "$work/ffmpeg/"
    cp config.h config_components.h "$work/metadata/"
)
{
    printf 'Platform: %s\nArchitecture: %s\nX86 assembly: %s\n' "$platform" "$architecture" "$assembly"
    "$CC" --version
    make --version
    meson --version
    ninja --version
    "$PKG_CONFIG" --version
    if command -v nasm >/dev/null; then nasm -v; fi
    if [[ "$platform" == windows-x64 ]]; then
        pacman -Q | awk '/^mingw-w64-ucrt-x86_64-(gcc|binutils|crt|headers|winpthreads|libwinpthread|libgcc|nasm|meson|ninja|pkgconf)/'
    else
        sw_vers
        xcrun --show-sdk-version
    fi
} > "$work/metadata/toolchain.txt"
if [[ "$platform" == windows-x64 ]]; then
    license_root=/ucrt64/share/licenses
    gcc_license="$license_root/libgcc"
    [[ -f "$gcc_license/COPYING.RUNTIME" ]] || gcc_license="$license_root/gcc-libs"
    mkdir -p "$work/metadata/windows-notices"
    cp "$gcc_license/COPYING.RUNTIME" "$gcc_license/COPYING3" "$work/metadata/windows-notices/"
    cp "$license_root/crt/COPYING.MinGW-w64-runtime.txt" "$work/metadata/windows-notices/"
    cp "$license_root/winpthreads/COPYING" "$work/metadata/windows-notices/COPYING.winpthreads"
fi
"$python" "$root/scripts/artifacts.py" package "$platform" "$cache" "$work" "$root/dist/$platform" --revision "${REVISION:-r1}"
