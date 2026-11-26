"""Export verified notice metadata to a self-contained, local HTML dashboard."""
import argparse
import json
import sqlite3
from pathlib import Path

TEMPLATE = Path(__file__).with_name("web") / "dashboard.html"


def export(db_path, output):
    if not db_path.is_file():
        raise FileNotFoundError("Build the notice index with python procurement/index.py first")
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        raw = db.execute("SELECT payload FROM release ORDER BY published, id, ocid")
        notices = [json.loads(row[0]) for row in raw]
    payload = json.dumps(notices, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    html = TEMPLATE.read_text().replace("/*__NOTICE_DATA__*/", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    print(f"{len(notices)} notices → {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("results/notices.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("results/dashboard.html"))
    args = parser.parse_args()
    export(args.db, args.output)
