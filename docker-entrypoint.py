#!/usr/bin/env python3
"""Hand the mounted data directory to the runtime user, then drop privileges.

The container starts as root only long enough to do this. A persistent volume
is mounted over /data at runtime, after the image is built, so a build-time
chown never reaches it — and an upgrade from an earlier root-running image
finds a database, attachments and backups that WorkbenchStore created with
mode 0600 and root ownership, which an unprivileged process cannot open at
all. Fixing ownership here, before exec'ing the service, is what makes
running unprivileged survive that upgrade.

Written in Python because the image already has it; reaching for gosu or
setpriv would add a dependency to do the same job.
"""

import grp
import os
import pwd
import sys

RUNTIME_USER = os.environ.get("WORKBENCH_USER", "workbench")
DATA_DIR = os.environ.get("WORKBENCH_DATA_DIR", "/data")


def own(path, uid, gid):
    """chown one path, ignoring anything that vanishes underneath us."""
    try:
        os.chown(path, uid, gid, follow_symlinks=False)
    except (FileNotFoundError, PermissionError):
        pass


def hand_over(directory, uid, gid):
    if not os.path.isdir(directory):
        return
    own(directory, uid, gid)
    for root, directories, files in os.walk(directory):
        for name in directories + files:
            own(os.path.join(root, name), uid, gid)


def main(argv):
    if not argv:
        print("docker-entrypoint: no command given", file=sys.stderr)
        return 2
    if os.geteuid() == 0:
        try:
            account = pwd.getpwnam(RUNTIME_USER)
        except KeyError:
            print(
                f"docker-entrypoint: no such user {RUNTIME_USER!r}", file=sys.stderr
            )
            return 2
        hand_over(DATA_DIR, account.pw_uid, account.pw_gid)
        # Groups first: once the uid is dropped these calls are no longer
        # permitted.
        os.setgid(account.pw_gid)
        try:
            os.initgroups(RUNTIME_USER, account.pw_gid)
        except (OSError, PermissionError):
            os.setgroups([account.pw_gid])
        os.setuid(account.pw_uid)
        os.environ.setdefault("HOME", "/tmp")
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
