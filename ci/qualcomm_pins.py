"""Compare CI-built Qualcomm components with the pins in DroidDeck's tools/qualcomm/runtime.json.

The pins record the phone-built Gamescope, Zink and WSI layer. CI rebuilds them from the same recipes in
another build root, so their bytes can differ. In `strict` mode any difference fails. In `rebuild` mode
runtime.json in the checkout is rewritten to the CI-built hashes, exactly as tools/qualcomm/README.md
describes after a deliberate rebuild, so the APK runtime-input check verifies the files this build packages.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


def describe(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def compare(source, lock):
    rows = []

    def check(component, name, pinned_sha, pinned_size, path, apply):
        if not path.is_file():
            raise SystemExit(f'CI did not produce {path}')
        sha, size = describe(path)
        rows.append({'component': component, 'file': name, 'pinned': pinned_sha, 'built': sha,
                     'match': sha == pinned_sha and (pinned_size is None or size == pinned_size)})
        apply(sha, size)

    gamescope = lock['gamescope']
    built = gamescope.get('build')
    if built:
        check('gamescope', 'gamescope', gamescope['member_sha256'], None, source / built['binary'],
              lambda sha, size: gamescope.update(member_sha256=sha))
        check('gamescope', 'source.tar.gz', built['source_sha256'], built['source_size'], source / built['source'],
              lambda sha, size: built.update(source_sha256=sha, source_size=size))

    if 'mesa' in lock:
        directory = source / lock['mesa']['directory']
        produced = json.loads((directory / 'build.json').read_text())['files']
        pinned = {entry['path']: entry for entry in lock['mesa']['files']}
        for entry in produced:
            old = pinned.get(entry['path'], {})
            check('zink', entry['path'], old.get('sha256', ''), old.get('size'), directory / entry['path'],
                  lambda sha, size: None)
        for name in sorted(set(pinned) - {entry['path'] for entry in produced}):
            rows.append({'component': 'zink', 'file': name, 'pinned': pinned[name]['sha256'], 'built': '',
                         'match': False})
        lock['mesa']['files'] = [{'path': e['path'], 'sha256': e['sha256'], 'size': e['size']} for e in produced]

    if 'wsi' in lock and 'build' in lock['wsi']:
        directory = source / lock['wsi']['build']['directory']
        for entry in lock['wsi']['files']:
            if entry.get('built'):
                check('wsi', entry['name'], entry['sha256'], entry['size'], directory / entry['name'],
                      lambda sha, size, entry=entry: entry.update(sha256=sha, size=size))
    return rows


def report(rows, status):
    lines = [f'Qualcomm components: **{status}**', '', '| Component | File | Pinned | CI-built | |',
             '| --- | --- | --- | --- | --- |']
    for row in rows:
        lines.append(f"| {row['component']} | `{row['file']}` | `{row['pinned'][:12] or '-'}` | "
                     f"`{row['built'][:12] or '-'}` | {'same' if row['match'] else 'differs'} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='DroidDeck checkout')
    parser.add_argument('--mode', choices=['rebuild', 'strict'], required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    lock_path = args.source / 'tools/qualcomm/runtime.json'
    lock = json.loads(lock_path.read_text())
    rows = compare(args.source, lock)
    exact = all(row['match'] for row in rows)
    status = 'exactly as pinned' if exact else ('re-pinned to the CI build' if args.mode == 'rebuild'
                                                else 'differ from the pins')
    args.report.write_text(report(rows, status))
    print(args.report.read_text())
    with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as output:
        output.write(f"status={'pinned' if exact else 'repinned' if args.mode == 'rebuild' else 'mismatch'}\n")
    if exact:
        return 0
    if args.mode == 'strict':
        return 1
    lock_path.write_text(json.dumps(lock, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
