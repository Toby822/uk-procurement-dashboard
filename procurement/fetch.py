"""Cache the first 14 pages of a bounded Find a Tender API query."""
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
WINDOW = {"updatedFrom": "2025-07-01T00:00:00Z",
          "updatedTo": "2025-07-15T00:00:00Z", "limit": 100}


def cache(max_pages=14):
    raw = Path("data/tenders")
    index = Path("data/tender_index")
    raw.mkdir(parents=True, exist_ok=True)
    index.mkdir(parents=True, exist_ok=True)
    url = API + "?" + urlencode(WINDOW)
    for number in range(1, max_pages + 1):
        filename = raw / f"{number:04}.json"
        if filename.exists():
            saved = json.loads(filename.read_text())
            if saved["source"] != url:
                raise ValueError("Cached page belongs to a different query")
            page = saved["page"]
        else:
            with urlopen(url, timeout=30) as response:
                page = json.load(response)
            temporary = filename.with_suffix(".tmp")
            temporary.write_text(json.dumps({"source": url, "page": page}, separators=(",", ":")))
            temporary.replace(filename)
        releases = [{key: row[key] for key in ("ocid", "id", "date", "tag")}
                    for row in page["releases"]]
        (index / filename.name).write_text(json.dumps(
            {"source": url, "page": {"releases": releases}}, separators=(",", ":")) + "\n")
        print(f"Cached page {number}", flush=True)
        url = page.get("links", {}).get("next")
        if not url:
            break


if __name__ == "__main__":
    cache()
