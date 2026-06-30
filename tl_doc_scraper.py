"""
TL Schema Documentation Scraper

Parses a schema.tl file, extracts constructors and methods, fetches per-entry
documentation from corefork.telegram.org, and writes a single JSON document.

Hot points (worth knowing):
- Uses a pooled requests.Session with urllib3 Retry, so transient 5xx / connection
  errors don't drop entries.
- Disk-caches every HTML response under .cache/scrape/ (one file per URL) so
  re-runs and CI iterations skip the network entirely.
- All console output is ASCII-only, so the script runs cleanly on Windows
  consoles (cp1252) where the previous version crashed on the first '✓'.
- Writes output via temp-file + atomic rename so a Ctrl-C mid-save doesn't
  truncate the JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Force UTF-8 on Windows consoles so we never repeat the cp1252 crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


BASE_URL = "https://corefork.telegram.org"
DEFAULT_CACHE_DIR = ".cache/scrape"


@dataclass
class FieldInfo:
    name: str
    type: str
    description: str = ""


@dataclass
class ErrorInfo:
    code: str
    type: str
    description: str


@dataclass
class TLEntry:
    name: str
    category: str  # "constructor" or "method"
    description: str = ""
    fields: list[FieldInfo] = field(default_factory=list)
    result_type: str = ""
    can_be_used_by: list[str] = field(default_factory=list)
    business_connection: bool = False
    errors: list[ErrorInfo] = field(default_factory=list)
    related_pages: list[str] = field(default_factory=list)
    raw_tl: str = ""


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def make_session(pool_size: int) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=retry,
    )
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": "TlRef-scraper/2.0 (+https://github.com/AmarnathCJD/tl-ref)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate",
    })
    return s


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def cache_path(cache_dir: Optional[Path], category: str, name: str) -> Optional[Path]:
    if cache_dir is None:
        return None
    # Replace dots in namespaced names so we don't create accidental subdirs.
    safe = name.replace("/", "_").replace("\\", "_")
    return cache_dir / category / f"{safe}.html"


def cached_get(session: requests.Session, url: str, cache_file: Optional[Path],
               timeout: float) -> Optional[str]:
    if cache_file is not None and cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception:
            pass  # fall through and re-fetch
    resp = session.get(url, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    text = resp.text
    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8")
        except Exception:
            pass
    return text


# ---------------------------------------------------------------------------
# Schema parsing
# ---------------------------------------------------------------------------

NAME_RE = r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?"
DEF_RE = re.compile(rf"^({NAME_RE})#([0-9a-fA-F]+)\s*(.*?)\s*=\s*({NAME_RE})\s*;?\s*$")
PARAM_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*):([^\s]+)")
LAYER_RE = re.compile(r"\bLAYER\s+(\d+)")


def parse_tl_definition(line: str) -> tuple[Optional[str], list[FieldInfo], Optional[str]]:
    m = DEF_RE.match(line)
    if not m:
        return None, [], None
    name = m.group(1)
    params_str = m.group(3)
    result_type = m.group(4)
    fields: list[FieldInfo] = []
    for pm in PARAM_RE.finditer(params_str):
        ftype = pm.group(2)
        if ftype == "#":
            continue  # flags marker, not a real field
        fields.append(FieldInfo(name=pm.group(1), type=ftype, description=""))
    return name, fields, result_type


def parse_schema(filepath: str) -> tuple[list[str], list[str], dict, Optional[int]]:
    """
    One pass over schema.tl. Returns:
      (constructors, methods, definitions, layer)
    """
    constructors: list[str] = []
    methods: list[str] = []
    definitions: dict = {}
    layer: Optional[int] = None
    in_functions = False

    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("//"):
                m = LAYER_RE.search(line)
                if m and layer is None:
                    layer = int(m.group(1))
                continue
            if line == "---functions---":
                in_functions = True
                continue
            if line == "---types---":
                in_functions = False
                continue
            name, fields, result_type = parse_tl_definition(line)
            if not name:
                continue
            definitions[name] = {
                "fields": fields,
                "result_type": result_type,
                "raw_tl": line,
            }
            if in_functions:
                methods.append(name)
            else:
                constructors.append(name)
    return constructors, methods, definitions, layer


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------

def text_with_spaces(element) -> str:
    if element is None:
        return ""
    text = element.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_description(dev_content) -> str:
    """
    The first <p> is sometimes a deprecation / scheduling note. Collect every
    <p> before the first <h3>, joined with single spaces, and use the first
    non-trivial paragraph (>= 20 chars) as the headline description plus any
    follow-up sentences.
    """
    if dev_content is None:
        return ""
    parts: list[str] = []
    for child in dev_content.children:
        name = getattr(child, "name", None)
        if name == "h3":
            break
        if name == "p":
            t = text_with_spaces(child)
            if t:
                parts.append(t)
    if not parts:
        return ""
    # Prefer the first paragraph that isn't an obvious banner.
    BANNERS = ("warning:", "note:", "this method is", "this page is")
    primary = next(
        (p for p in parts if len(p) >= 20 and not p.lower().startswith(BANNERS)),
        parts[0],
    )
    return primary


def extract_raw_tl(soup: BeautifulSoup, name: str) -> str:
    # The TL definition line is usually in a <pre><code>...</code></pre>.
    for code in soup.find_all("code"):
        text = code.get_text()
        for line in text.split("\n"):
            if name in line and "#" in line and "=" in line:
                return line.strip()
    return ""


def extract_table_rows(table, max_cols: int) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cols = tr.find_all(["td", "th"])
        if not cols:
            continue
        if tr.find("th") and not tr.find("td"):
            continue  # header row
        values = [text_with_spaces(c) for c in cols[:max_cols]]
        # Pad short rows
        while len(values) < max_cols:
            values.append("")
        rows.append(values)
    return rows


def extract_result_type(soup: BeautifulSoup) -> str:
    # Try the explicit anchor first.
    anchor = soup.find("h3", id="result") or soup.find("h3", id="type")
    if anchor:
        nxt = anchor.find_next_sibling()
        if nxt is not None:
            link = nxt.find("a") if hasattr(nxt, "find") else None
            return (link or nxt).get_text(strip=True)
    # Fall back to header text match.
    for h3 in soup.find_all("h3"):
        if h3.get_text(strip=True).lower() in ("result", "type"):
            nxt = h3.find_next_sibling()
            if nxt is not None:
                link = nxt.find("a") if hasattr(nxt, "find") else None
                return (link or nxt).get_text(strip=True)
    return ""


CAN_USE_PATTERNS = [
    (re.compile(r"both users and bots can use this method", re.I), ["users", "bots"]),
    (re.compile(r"only users can use this method", re.I), ["users"]),
    (re.compile(r"only bots can use this method", re.I), ["bots"]),
    (re.compile(r"bots can use this method", re.I), ["bots"]),
    (re.compile(r"users can use this method", re.I), ["users"]),
]


def detect_usage(page_text: str) -> list[str]:
    for pat, who in CAN_USE_PATTERNS:
        if pat.search(page_text):
            return who
    return []


def parse_page(html: str, name: str, category: str) -> TLEntry:
    soup = BeautifulSoup(html, "html.parser")
    entry = TLEntry(name=name, category=category)

    dev_content = soup.find("div", id="dev_page_content")
    entry.description = extract_description(dev_content)
    entry.raw_tl = extract_raw_tl(soup, name)

    # Tables: parameters / errors.
    for table in soup.find_all("table"):
        header = table.find_previous("h3")
        if not header:
            continue
        htxt = header.get_text(strip=True).lower()
        if "parameter" in htxt:
            for row in extract_table_rows(table, 3):
                name_v, type_v, desc_v = row[0], row[1], row[2]
                if name_v and type_v:
                    entry.fields.append(FieldInfo(name=name_v, type=type_v, description=desc_v))
        elif "error" in htxt or "possible error" in htxt:
            for row in extract_table_rows(table, 3):
                code_v, type_v, desc_v = row[0], row[1], row[2]
                if code_v and type_v:
                    entry.errors.append(ErrorInfo(code=code_v, type=type_v, description=desc_v))

    entry.result_type = extract_result_type(soup)

    page_text = soup.get_text(" ", strip=True)
    entry.can_be_used_by = detect_usage(page_text)
    entry.business_connection = "business connection" in page_text.lower()

    # Related pages: collect <h4>/<a> until the next <h3>.
    for h3 in soup.find_all("h3"):
        if "related page" in h3.get_text(strip=True).lower():
            sib = h3.find_next_sibling()
            while sib is not None and getattr(sib, "name", None) != "h3":
                if getattr(sib, "name", None) == "h4":
                    a = sib.find("a")
                    if a:
                        entry.related_pages.append(a.get_text(strip=True))
                sib = sib.find_next_sibling()
            break

    return entry


def entry_from_schema(name: str, category: str, sdef: dict) -> TLEntry:
    return TLEntry(
        name=name,
        category=category,
        description="",
        fields=list(sdef.get("fields", [])),
        result_type=sdef.get("result_type", "") or "",
        raw_tl=sdef.get("raw_tl", "") or "",
    )


def merge_schema_fallback(entry: TLEntry, sdef: Optional[dict]) -> TLEntry:
    """If the scraped page didn't yield params or raw_tl, fill from schema."""
    if not sdef:
        return entry
    if not entry.raw_tl:
        entry.raw_tl = sdef.get("raw_tl", "") or ""
    if not entry.fields:
        entry.fields = list(sdef.get("fields", []))
    if not entry.result_type:
        entry.result_type = sdef.get("result_type", "") or ""
    return entry


# ---------------------------------------------------------------------------
# Fetch + scrape orchestration
# ---------------------------------------------------------------------------

def fetch_one(session: requests.Session, name: str, category: str,
              cache_dir: Optional[Path], timeout: float,
              schema_defs: dict) -> tuple[Optional[TLEntry], str]:
    url = f"{BASE_URL}/{category}/{name}"
    sdef = schema_defs.get(name)
    try:
        html = cached_get(session, url, cache_path(cache_dir, category, name), timeout)
    except requests.RequestException as e:
        if sdef:
            return entry_from_schema(name, category, sdef), f"network-error ({e.__class__.__name__})"
        return None, f"network-error ({e.__class__.__name__})"

    if html is None:
        # 404. Fall back to schema if we have it.
        if sdef:
            return entry_from_schema(name, category, sdef), "404 (schema fallback)"
        return None, "404"

    try:
        entry = parse_page(html, name, category)
    except Exception as e:
        if sdef:
            return entry_from_schema(name, category, sdef), f"parse-error ({e.__class__.__name__})"
        return None, f"parse-error ({e.__class__.__name__})"

    entry = merge_schema_fallback(entry, sdef)
    return entry, "ok"


def entry_to_dict(entry: TLEntry) -> dict:
    return {
        "name": entry.name,
        "category": entry.category,
        "description": entry.description,
        "fields": [{"name": f.name, "type": f.type, "description": f.description} for f in entry.fields],
        "result_type": entry.result_type,
        "can_be_used_by": entry.can_be_used_by,
        "business_connection": entry.business_connection,
        "errors": [{"code": e.code, "type": e.type, "description": e.description} for e in entry.errors],
        "related_pages": entry.related_pages,
        "raw_tl": entry.raw_tl,
    }


def render_bar(done: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return ""
    frac = done / total
    filled = int(frac * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {done}/{total} ({frac*100:5.1f}%)"


def atomic_write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def scrape_all(schema_path: str, output_path: str, max_workers: int,
               cache_dir: Optional[Path], timeout: float, verbose: bool) -> None:
    print(f"Parsing schema: {schema_path}")
    constructors, methods, schema_defs, layer = parse_schema(schema_path)
    print(f"Found {len(constructors)} constructors, {len(methods)} methods (layer {layer})")

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        print(f"Cache directory: {cache_dir.resolve()}")
    else:
        print("Cache disabled")

    tasks: list[tuple[str, str]] = (
        [(n, "constructor") for n in constructors] +
        [(n, "method") for n in methods]
    )
    print(f"Total items to fetch: {len(tasks)}")

    results: dict = {
        "constructors": [],
        "methods": [],
        "metadata": {
            "total_constructors": len(constructors),
            "total_methods": len(methods),
            "layer": layer,
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": BASE_URL,
            "fallback_source": "schema.tl",
        },
    }

    session = make_session(max_workers)
    completed = 0
    failures: list[tuple[str, str, str]] = []
    schema_fallback = 0
    started = time.time()
    last_render = 0.0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_one, session, n, c, cache_dir, timeout, schema_defs): (n, c)
            for n, c in tasks
        }
        for fut in as_completed(futures):
            name, category = futures[fut]
            completed += 1
            try:
                entry, status = fut.result()
            except Exception as e:
                entry, status = None, f"executor-error ({e.__class__.__name__})"

            if entry is not None:
                bucket = "constructors" if category == "constructor" else "methods"
                results[bucket].append(entry_to_dict(entry))
                if "fallback" in status or status.startswith("network-error") or status.startswith("parse-error"):
                    schema_fallback += 1
            else:
                failures.append((category, name, status))

            # Live progress: redraw at most twice a second.
            now = time.time()
            if verbose or now - last_render > 0.5 or completed == len(tasks):
                bar = render_bar(completed, len(tasks))
                rate = completed / max(now - started, 1e-6)
                eta = (len(tasks) - completed) / max(rate, 1e-6)
                sys.stdout.write(
                    f"\r{bar}  rate={rate:5.1f}/s  eta={int(eta):>4}s  fallbacks={schema_fallback}  fails={len(failures)}"
                )
                sys.stdout.flush()
                last_render = now

    print()  # finish progress line
    results["metadata"]["successful"] = len(results["constructors"]) + len(results["methods"])
    results["metadata"]["failed"] = len(failures)
    results["metadata"]["schema_fallback_used"] = schema_fallback

    # Sort by name for stable diffs.
    results["constructors"].sort(key=lambda x: x["name"])
    results["methods"].sort(key=lambda x: x["name"])

    print(f"Writing {output_path}")
    atomic_write_json(output_path, results)

    elapsed = time.time() - started
    print(f"Done in {elapsed:.1f}s")
    print(f"  Constructors: {len(results['constructors'])}")
    print(f"  Methods: {len(results['methods'])}")
    print(f"  Schema fallbacks used: {schema_fallback}")
    print(f"  Failed: {len(failures)}")
    if failures:
        sample = failures[:10]
        print("  First failures:")
        for cat, n, s in sample:
            print(f"    [{cat}] {n}: {s}")


def main() -> None:
    p = argparse.ArgumentParser(description="Scrape TL schema documentation from corefork.telegram.org")
    p.add_argument("schema", help="Path to schema.tl file")
    p.add_argument("-o", "--output", default="output.json", help="Output JSON file path")
    p.add_argument("-w", "--workers", type=int, default=16, help="Concurrent workers (default: 16)")
    p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help=f"Directory for response cache (default: {DEFAULT_CACHE_DIR})")
    p.add_argument("--no-cache", action="store_true", help="Disable disk cache")
    p.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds")
    p.add_argument("--verbose", action="store_true", help="Print one line per item instead of a single progress bar")
    args = p.parse_args()

    cache_dir = None if args.no_cache else Path(args.cache_dir)
    scrape_all(
        schema_path=args.schema,
        output_path=args.output,
        max_workers=args.workers,
        cache_dir=cache_dir,
        timeout=args.timeout,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
