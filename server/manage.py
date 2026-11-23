"""Server administration.

    python -m server.manage init                      # create the folders and the two keys
    python -m server.manage add-clinician <username>  # add one, or set a new password (asked twice)
    python -m server.manage deactivate <username>
    python -m server.manage export [--keep-ids] > export.json   # de-identified clinical data
    python -m server.manage audit [record_id]
"""
import argparse
import getpass
import json
import sys

from . import sanitize
from .auth import hash_password
from .config import load_settings
from .crypto import Box, create_keys
from .store import Store


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m server.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add-clinician"); a.add_argument("username")
    a.add_argument("--password-stdin", action="store_true", help="read the password from stdin (for scripts)")
    d = sub.add_parser("deactivate"); d.add_argument("username")
    e = sub.add_parser("export"); e.add_argument("--keep-ids", action="store_true")
    u = sub.add_parser("audit"); u.add_argument("record_id", nargs="?")
    args = ap.parse_args(argv)
    s = load_settings()

    if args.cmd == "init":
        s.data_dir.mkdir(parents=True, exist_ok=True)
        for p in create_keys(s.key_dir):
            print(f"created {p}")
        Store(s.db_path, Box.load(s.key_dir))
        print(f"database {s.db_path}")
        print("Back up the keys separately from the database: without data.key the records cannot be read.")
        return 0
    store = Store(s.db_path, Box.load(s.key_dir))
    if args.cmd == "add-clinician":
        if args.password_stdin:
            pw = sys.stdin.readline().rstrip("\n")
        else:
            pw = getpass.getpass("password: ")
            if pw != getpass.getpass("again: "):
                print("the passwords differ", file=sys.stderr)
                return 1
        store.add_clinician(args.username, hash_password(pw))
        print(f"clinician {args.username} saved")
    elif args.cmd == "deactivate":
        print("deactivated" if store.deactivate_clinician(args.username) else "no such clinician")
    elif args.cmd == "export":
        json.dump(sanitize.export(store, keep_ids=args.keep_ids), sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif args.cmd == "audit":
        for row in store.audit_log(args.record_id):
            print(row["at"], row["actor"], row["action"], row["record_id"] or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
