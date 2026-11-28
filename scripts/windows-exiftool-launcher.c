/* Windows bootstrap for the sibling ExifTool and CasaMemo Perl runtime. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

typedef int (__cdecl *RunPerl)(int, char **, char **);

static wchar_t runtime[MAXSHORT + 1];
static wchar_t path[MAXSHORT + 1];

static void runtime_path(const wchar_t *name)
{
    wcscpy(path, runtime);
    wcscat(path, name);
}

static char *utf8(const wchar_t *value)
{
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, NULL, 0, NULL, NULL);
    char *result = size > 0 ? malloc((size_t)size) : NULL;
    if (!result || !WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, result, size, NULL, NULL)) {
        fputs("ExifTool could not encode a command-line argument as UTF-8.\n", stderr);
        exit(1);
    }
    return result;
}

int wmain(int argc, wchar_t **argv)
{
    DWORD length = GetModuleFileNameW(NULL, runtime, ARRAYSIZE(runtime));
    if (!length || length >= ARRAYSIZE(runtime) - 64) {
        fputs("ExifTool could not locate its runtime directory.\n", stderr);
        return 1;
    }
    wchar_t *filename = wcsrchr(runtime, L'\\');
    if (!filename)
        return 1;
    wcscpy(filename + 1, L"exiftool_files\\");

    /* Only the sibling runtime and system directories may supply native DLLs. */
    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)
            || !AddDllDirectory(runtime)) {
        fprintf(stderr, "ExifTool could not set the DLL search path (Windows error %lu).\n", GetLastError());
        return 1;
    }
    runtime_path(L"perl544.dll");
    HMODULE library = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
    if (!library) {
        fprintf(stderr, "ExifTool could not load its Perl runtime (Windows error %lu).\n", GetLastError());
        return 1;
    }
    RunPerl run_perl = (RunPerl)GetProcAddress(library, "RunPerl");
    if (!run_perl) {
        fputs("ExifTool could not find the Perl runtime entry point.\n", stderr);
        return 1;
    }

    /* Avoid importing modules or interpreter options from installed Perls. */
    _putenv("PERL5LIB=");
    _putenv("PERLLIB=");
    _putenv("PERL5OPT=");
    _putenv("PERL_USE_UNSAFE_INC=");

    char **arguments = calloc((size_t)argc + 7, sizeof(*arguments));
    if (!arguments) {
        fputs("ExifTool could not allocate its argument list.\n", stderr);
        return 1;
    }
    int count = 0;
    arguments[count++] = utf8(argv[0]);
    arguments[count++] = "-I";
    runtime_path(L"lib");
    arguments[count++] = utf8(path);
    runtime_path(L"exiftool.pl");
    arguments[count++] = utf8(path);
    arguments[count++] = "-xpath";
    int index = 1;
    /* ExifTool handles leading config options before parsing its other options. */
    while (index + 1 < argc && _wcsicmp(argv[index], L"-config") == 0) {
        arguments[count++] = utf8(argv[index++]);
        arguments[count++] = utf8(argv[index++]);
    }
    arguments[count++] = "-charset";
    arguments[count++] = "filename=utf8";
    while (index < argc)
        arguments[count++] = utf8(argv[index++]);
    return run_perl(count, arguments, _environ);
}
