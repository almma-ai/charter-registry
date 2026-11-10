"""
registry validate --base <dir> --head <dir> --author <login> [--out comment.md]
registry publish  [--repo .] [--out site]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_validate(a):
    import json
    from .validate import run
    files = json.loads(Path(a.pr_files).read_text()) if a.pr_files else None
    ok, md = run(Path(a.base), Path(a.head), a.author, a.schema, files)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(md)
    sys.exit(0 if ok else 1)


def cmd_publish(a):
    from .publish import build_site
    recs = build_site(Path(a.repo), Path(a.out))
    print(f"wrote {a.out}: {len(recs)} entr{'y' if len(recs) == 1 else 'ies'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="registry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check a pull request and write the comment")
    v.add_argument("--base", required=True, help="checkout of the target branch")
    v.add_argument("--head", required=True, help="checkout of the pull request (read as data only)")
    v.add_argument("--author", required=True, help="pull request author's GitHub login")
    v.add_argument("--schema", help="local charter schema instead of fetching it")
    v.add_argument("--pr-files", help="JSON list from GET /pulls/{n}/files (default: compare the two trees)")
    v.add_argument("--out", help="write the comment here")
    v.set_defaults(fn=cmd_validate)
    p = sub.add_parser("publish", help="build the site from entries and git history")
    p.add_argument("--repo", default=".")
    p.add_argument("--out", default="site")
    p.set_defaults(fn=cmd_publish)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
