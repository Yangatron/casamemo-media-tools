# Build the pinned Brotli XS with the UCRT64 toolchain and local static libraries.
use strict;
use warnings;
use ExtUtils::MakeMaker;

WriteMakefile(
    NAME         => 'IO::Compress::Brotli',
    VERSION_FROM => 'lib/IO/Compress/Brotli.pm',
    LICENSE      => 'perl',
    INC          => '-Ibrotli/c/include',
    MYEXTLIB     => 'brotli-build/libbrotli.a',
    PM           => {
        'lib/IO/Compress/Brotli.pm'   => '$(INST_LIB)/IO/Compress/Brotli.pm',
        'lib/IO/Uncompress/Brotli.pm' => '$(INST_LIB)/IO/Uncompress/Brotli.pm',
    },
);
