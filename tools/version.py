#!/usr/bin/env python3
"""Stamp the next desktop build in Git's commit index, without making a commit."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'config/hypr/updates'))
from release_version import SOURCE_PATH, PATTERN, parse


def git(*args, required=True):
    result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True)
    if result.returncode and required:
        raise RuntimeError(result.stderr.strip() or 'Git command failed: '+' '.join(args))
    return result.stdout.strip() if result.returncode == 0 else None


def build(value):
    return int(re.fullmatch(PATTERN, parse(value))[4])


def parents():
    result = []
    head = git('rev-parse', '--verify', 'HEAD', required=False)
    if head: result.append(head)
    merge = Path(git('rev-parse', '--git-path', 'MERGE_HEAD'))
    if not merge.is_absolute(): merge = ROOT/merge
    if merge.is_file(): result.extend(merge.read_text().split())
    return result


def next_version():
    indexed = git('show', ':'+SOURCE_PATH, required=False)
    candidate = parse(indexed if indexed is not None else (ROOT/SOURCE_PATH).read_text())
    commits = parents()
    if not commits: return candidate
    previous = [git('show', commit+':'+SOURCE_PATH, required=False) for commit in commits]
    counts = [build(value) for value in previous if value is not None]
    # Seed an old checkout from its actual history; later shallow clones can use
    # the committed build number. Failed/retried commits do not consume numbers.
    if git('rev-parse', '--is-shallow-repository') == 'false':
        counts.append(int(git('rev-list', '--count', *commits)))
    if not counts: raise RuntimeError('Fetch full Git history before numbering this older checkout.')
    match = re.fullmatch(PATTERN, candidate)
    return '.'.join(match.groups()[:3])+'.'+str(max(counts)+1)+(match[5] or '')


def bump():
    path = ROOT/SOURCE_PATH
    indexed = git('show', ':'+SOURCE_PATH, required=False)
    if indexed is not None and path.read_text().strip() != indexed:
        raise RuntimeError('VERSION has unstaged edits. Stage or undo them before committing.')
    value = next_version()
    path.write_text(value+'\n')
    git('add', '--', SOURCE_PATH)
    print('Hyper Fusion release '+value, file=sys.stderr)


def install_hooks():
    configured = git('config', '--get', 'core.hooksPath', required=False)
    if configured and configured != '.githooks':
        raise RuntimeError('An existing hooksPath is configured. Add tools/version.py --bump to its commit hooks.')
    if not configured:
        hooks = Path(git('rev-parse', '--git-path', 'hooks'))
        if not hooks.is_absolute(): hooks = ROOT/hooks
        if hooks.exists() and any(p.is_file() and not p.name.endswith('.sample') for p in hooks.iterdir()):
            raise RuntimeError('Existing Git hooks were kept. Integrate tools/version.py --bump before changing hooksPath.')
    git('config', '--local', 'core.hooksPath', '.githooks')
    print('Automatic release numbering enabled for commits in this checkout.')


def check(commit):
    value = parse(git('show', commit+':'+SOURCE_PATH))
    ancestors = git('rev-list', '--parents', '-n', '1', commit).split()[1:]
    for parent in ancestors:
        previous = git('show', parent+':'+SOURCE_PATH, required=False)
        if previous is not None and build(value) <= build(previous):
            raise RuntimeError('Release number did not advance. Enable hooks with python3 tools/version.py --install-hooks.')
    print(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--install-hooks', action='store_true')
    action.add_argument('--bump', action='store_true', help='Used automatically by the commit hooks.')
    action.add_argument('--check', metavar='COMMIT', help='Verify a committed release number.')
    args = parser.parse_args()
    try:
        if args.install_hooks: install_hooks()
        elif args.bump: bump()
        elif args.check: check(args.check)
        else: print(parse((ROOT/SOURCE_PATH).read_text()))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__': main()
