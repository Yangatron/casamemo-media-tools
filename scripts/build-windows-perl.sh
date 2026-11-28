#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 || ${MSYSTEM:-} != UCRT64 ]]; then
    echo 'usage: build-windows-perl.sh RECIPE PREREQUISITE FIX NATIVE_MAKE_BIN JOBS (in UCRT64)' >&2
    exit 2
fi

srcdir=$(cd -- "$1" && pwd -P)
prerequisite=$(realpath -- "$2")
fix=$(realpath -- "$3")
casamemo_make_bin=$(cd -- "$4" && pwd -P)
export JOBS=$5 CC=gcc CXX=g++
export MINGW_PACKAGE_PREFIX=mingw-w64-ucrt-x86_64 MINGW_PREFIX=/ucrt64
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=1795132800
unset PERL5LIB PERLLIB PERL5OPT PERL_USE_UNSAFE_INC CFLAGS CPPFLAGS LDFLAGS MAKEFLAGS MFLAGS
pkgdirbase="$srcdir/package"
maps="$srcdir/link-maps"
[[ $JOBS =~ ^[1-9][0-9]*$ && -f "$casamemo_make_bin/mingw32-make.exe" ]]
[[ ! -e "$srcdir/build-UCRT64" && ! -e "$pkgdirbase" && ! -e "$maps" ]]
mkdir -- "$pkgdirbase" "$maps"

msg2() { printf '%s\n' "$1"; }
check_option() { return 1; }

# Keep the verified recipe intact. Its native cmd.exe step also needs the
# verified native make executable when building in a standalone workspace.
path_line='    local path="${sysroot}/system32:${sysroot}:${MINGW_PREFIX}/bin"'
[[ $(grep -Fxc -- "$path_line" "$srcdir/PKGBUILD") == 1 ]]
source <(sed 's@^\(    local path=".*\)"$@\1:${casamemo_make_bin}"@' "$srcdir/PKGBUILD")
prepare

cd -- "$srcdir/build-UCRT64"
patch --batch --forward --fuzz=0 -p1 -i "$prerequisite"
patch --batch --forward --fuzz=0 -p1 -i "$fix"
patch --batch --dry-run --reverse --fuzz=0 -p1 -i "$fix"

# The runtime's perl -V reports this identity. The native linker uses each
# output's name when given a map directory. MakeMaker retains the directory.
[[ $(grep -Fxc 'static const char * const local_patches[] = {' patchlevel.h) == 1 ]]
sed -i '/^static const char \* const local_patches\[\] = {/{
    n
    a\        ,"CasaMemo MSYS2 UCRT64 r1 (CVE-2026-15534)"
}' patchlevel.h
[[ $(grep -Ec '^LINK_FLAGS[[:space:]]*= \$\(LINK_DBG\) -L' win32/GNUmakefile) == 1 ]]
map_dir=$(cygpath -m "$maps")
sed -i "/^LINK_FLAGS[[:space:]]*= \$(LINK_DBG) -L/s|\$| -Wl,-Map=$map_dir|" win32/GNUmakefile

build
_make test-prep
(
    cd -- "$srcdir/build-UCRT64/t"
    PATH="$MINGW_PREFIX/bin:$PATH" ../perl.exe -I../lib harness \
        re/pat.t re/pat_advanced.t re/regexp_normal.t re/regexp_notrie.t \
        ../cpan/Win32API-File/t/file.t ../cpan/Compress-Raw-Bzip2/t/01bzip2.t
)
_make install
