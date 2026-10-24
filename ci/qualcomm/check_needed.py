"""Check that CI-built Qualcomm binaries load against the DroidDeck runtime.

Fails when a file needs a library the runtime lacks (tools/gamescope/runtime-sonames.txt) or a newer glibc
symbol version than the phone build root offered. Library sets that differ from the phone build are
reported as warnings. Prints a Markdown report.
"""
import re
import subprocess
import sys
from pathlib import Path


def elf_files(root):
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink() and path.read_bytes()[:4] == b'\x7fELF':
            yield path


def needed(path):
    dynamic = subprocess.run(['readelf', '-d', str(path)], capture_output=True, text=True, check=True).stdout
    return sorted(re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', dynamic))


def glibc_max(path):
    versions = subprocess.run(['readelf', '-V', str(path)], capture_output=True, text=True, check=True).stdout
    found = {tuple(int(part) for part in v.split('.')) for v in re.findall(r'GLIBC_(\d+\.\d+(?:\.\d+)?)', versions)}
    return max(found) if found else (0,)


def parse_expected(path):
    limit, libraries = (0,), {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        key, _, value = line.partition(':')
        if key == 'glibc-max':
            limit = tuple(int(part) for part in value.strip().split('.'))
        else:
            libraries[key.strip()] = value.split()
    return limit, libraries


def main(root, sonames, expected):
    runtime = set(sonames.read_text().split())
    limit, phone = parse_expected(expected)
    provided = {path.name for path in root.rglob('*') if path.is_file()}
    errors, warnings = [], []
    print('| File | glibc | Needed |')
    print('| --- | --- | --- |')
    for path in elf_files(root):
        relative = path.relative_to(root).as_posix()
        libraries = needed(path)
        newest = glibc_max(path)
        print(f'| `{relative}` | {".".join(map(str, newest))} | {" ".join(libraries)} |')
        missing = [lib for lib in libraries if lib not in runtime and lib not in provided]
        if missing:
            errors.append(f'{relative} needs libraries the runtime lacks: {" ".join(missing)}')
        if newest > limit:
            errors.append(f'{relative} needs GLIBC_{".".join(map(str, newest))}; the phone build root offered '
                          f'{".".join(map(str, limit))}')
        if relative in phone and sorted(phone[relative]) != libraries:
            added = sorted(set(libraries) - set(phone[relative]))
            removed = sorted(set(phone[relative]) - set(libraries))
            warnings.append(f'{relative} links differently from the phone build: '
                            f'added {" ".join(added) or "nothing"}, dropped {" ".join(removed) or "nothing"}')
    print()
    for warning in warnings:
        print(f'- Warning: {warning}')
    for error in errors:
        print(f'- Error: {error}')
    if not warnings and not errors:
        print('Every file links the same libraries as the phone build, all present in the runtime.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
