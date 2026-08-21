#!/usr/bin/env python3
"""Safely extract one libgphoto2 source tree from a tar archive."""

from __future__ import print_function

import os
import sys
import tarfile


def unsafe_path(name):
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return normalized.startswith("/") or ".." in parts


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: safe_extract_source.py ARCHIVE DESTINATION")
    archive, destination = sys.argv[1:]
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        roots = set()
        for member in members:
            if unsafe_path(member.name) or member.isdev() or member.isfifo():
                raise SystemExit("unsafe source archive member: %s" % member.name)
            normalized = member.name.replace("\\", "/").strip("/")
            if normalized:
                roots.add(normalized.split("/", 1)[0])
            if member.issym() or member.islnk():
                if unsafe_path(member.linkname) or os.path.isabs(member.linkname):
                    raise SystemExit("unsafe source archive link: %s" % member.name)
        if len(roots) != 1:
            raise SystemExit("source archive must contain exactly one top-level directory")
        source.extractall(destination)
    print(os.path.join(destination, next(iter(roots))))


if __name__ == "__main__":
    main()
