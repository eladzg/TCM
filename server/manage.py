"""Server administration.

    python -m server.manage init                      # create the folders and the two keys
    python -m server.manage add-clinician <username>  # add one, or set a new password (asked twice)
    python -m server.manage deactivate <username>
    python -m server.manage export [--keep-ids] > export.json   # de-identified clinical data
    python -m server.manage audit [record_id]
    python -m server.manage kb-export [path]          # clinician KB decisions -> kb/approvals/decisions.json
    python -m server.manage kb-verify                 # check the decision log's hash chain and signatures
    python -m server.manage backup                    # an encrypted backup now (data/server/backups/)
    python -m server.manage restore-check [file]      # open a backup in a temporary folder and check it
    python -m server.manage wa-token                  # a random verify token for the WhatsApp webhook
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

from . import approvals, backup, sanitize
from .auth import hash_password
from .config import ROOT, load_settings
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
    k = sub.add_parser("kb-export"); k.add_argument("path", nargs="?", type=Path, default=ROOT / "kb" / "approvals" / "decisions.json")
    sub.add_parser("kb-verify")
    sub.add_parser("backup")
    rc = sub.add_parser("restore-check"); rc.add_argument("file", nargs="?", type=Path)
    sub.add_parser("wa-token")
    args = ap.parse_args(argv)
    s = load_settings()

    if args.cmd == "init":
        s.data_dir.mkdir(parents=True, exist_ok=True)
        for p in create_keys(s.key_dir):
            print(f"created {p}")
        approvals.load_sign_key(s.key_dir)
        backup.load_key(s.key_dir)
        Store(s.db_path, Box.load(s.key_dir))
        print(f"database {s.db_path}")
        print("Back up the keys separately from the database: without data.key the records cannot be read.")
        return 0
    if args.cmd == "wa-token":
        from .whatsapp import new_verify_token
        print(new_verify_token())
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
    elif args.cmd in ("kb-export", "kb-verify"):
        dec = approvals.Decisions(store, approvals.load_sign_key(s.key_dir, create=False))
        ok, msg = dec.verify()
        print(msg, file=sys.stderr)
        if not ok:
            return 1
        if args.cmd == "kb-export":
            args.path.parent.mkdir(parents=True, exist_ok=True)
            args.path.write_text(json.dumps(dec.export(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {args.path}; rebuild with tools/interview/build_interview.py and tools/treatment/build_treatment.py")
    elif args.cmd == "backup":
        from .practice import Practice
        Practice(store, s.timezone)   # make sure the practice tables exist before copying
        print(backup.make(s))
    elif args.cmd == "restore-check":
        path = args.file or backup.latest(s)
        if not path:
            print("no backup yet", file=sys.stderr)
            return 1
        print(json.dumps(backup.check(s, path), ensure_ascii=False, indent=1))
    elif args.cmd == "audit":
        for row in store.audit_log(args.record_id):
            print(row["at"], row["actor"], row["action"], row["record_id"] or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
