"""Verify the cached sample, historical cutoffs and recovery after a killed import."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .index import apply_page, connect, history, load, stamp, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/tender_index"))
    parser.add_argument("--db", type=Path, default=Path("results/notices.sqlite3"))
    parser.add_argument("--results", type=Path, default=Path("results/metrics.json"))
    parser.add_argument("--as-of", nargs=2, metavar=("OCID", "TIMESTAMP"))
    parser.add_argument("--crash-test-child", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.crash_test_child:
        db = connect(args.db)
        inserts = 0
        def crash_halfway(statement):
            nonlocal inserts
            if statement.startswith("INSERT INTO release"):
                inserts += 1
                if inserts == 50:
                    os._exit(71)
        db.set_trace_callback(crash_halfway)
        apply_page(db, json.loads(args.crash_test_child.read_text()))
        raise RuntimeError("Expected to exit mid-transaction")
    if args.as_of:
        if not args.db.is_file():
            parser.error("Build the index before querying it")
        db = connect(args.db)
        try:
            print(json.dumps(history(db, *args.as_of), indent=2))
        finally:
            db.close()
        return
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(args.data.glob("[0-9][0-9][0-9][0-9].json"))[:14]
    if not files:
        raise ValueError("No cached pages")
    baseline = connect(":memory:")
    # Compare from an empty database on every run, and leave the verified index on disk.
    temp = TemporaryDirectory(dir=args.db.parent)
    work_path = Path(temp.name) / "build.sqlite3"
    db = connect(work_path)
    try:
        load(baseline, files)
        reference = state(baseline)
        target = len(files) // 2
        load(db, files[:target])
        prior = state(db)
        db.close()
        child = subprocess.run([sys.executable, "-m", "procurement.verify", "--db", str(work_path),
                                "--crash-test-child", str(files[target])], check=False)
        assert child.returncode == 71
        db = connect(work_path)
        assert state(db) == prior
        resumed_pages = load(db, files)
        assert resumed_pages == len(files) - target and state(db) == reference
        assert load(db, files) == 0
        assert load(db, reversed(files), replay=True) == len(files)
        assert state(db) == reference
        processes, = db.execute("SELECT COUNT(DISTINCT ocid) FROM release").fetchone()
        multi, = db.execute("SELECT COUNT(*) FROM (SELECT ocid FROM release GROUP BY ocid HAVING COUNT(*)>1)").fetchone()
        windows = [json.loads(file.read_text())["page"]["releases"] for file in files]
        expected = {}
        for page in windows:
            for release in page:
                expected.setdefault(release["ocid"], {})[release["id"]] = release
        sample = [ocid for ocid in sorted(expected) if len(expected[ocid]) > 1]
        verified_cutoffs = 0
        for ocid in sample:
            entries = list(expected[ocid].values())
            for item in entries:
                verified_cutoffs += 1
                published = stamp(item["date"])
                assert {row["id"] for row in history(db, ocid, published)} == {
                    row["id"] for row in entries if stamp(row["date"]) <= published}
        result = dict(pages=len(files), releases=reference[0], processes=processes,
                      processes_with_multiple_releases=multi, sha256=reference[1],
                      verified_histories=len(sample), verified_cutoffs=verified_cutoffs,
                      pages_skipped_on_restart=len(files) - resumed_pages, simulated_crash_exit_code=71,
                      restart_and_reverse_replay_match=True)
        args.results.write_text(json.dumps(result, indent=2) + "\n")
        print(result)
    finally:
        baseline.close()
        db.close()
    work_path.replace(args.db)
    temp.cleanup()


if __name__ == "__main__":
    main()
