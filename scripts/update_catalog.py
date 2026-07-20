"""Build the project catalog from multiple curated GitHub repositories."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

from parse_readme import normalize_url, parse_product_line, parse_readme


SOURCES = (
    {
        "id": "1c7/chinese-independent-developer",
        "name": "1c7 / CID",
        "url": "https://github.com/1c7/chinese-independent-developer",
        "raw_url": "https://raw.githubusercontent.com/1c7/chinese-independent-developer/master/README.md",
        "license": "未声明",
        "parser": "cid",
    },
    {
        "id": "DevEloLin/chinese-indie-vibe-coding",
        "name": "Vibe Coding 作品集",
        "url": "https://github.com/DevEloLin/chinese-indie-vibe-coding",
        "raw_url": "https://raw.githubusercontent.com/DevEloLin/chinese-indie-vibe-coding/main/README.md",
        "license": "CC0-1.0",
        "parser": "vibe",
    },
    {
        "id": "XiaomingX/1000-chinese-independent-developer-plus",
        "name": "独立项目精选",
        "url": "https://github.com/XiaomingX/1000-chinese-independent-developer-plus",
        "raw_url": "https://raw.githubusercontent.com/XiaomingX/1000-chinese-independent-developer-plus/main/README.md",
        "license": "Apache-2.0",
        "parser": "curated_table",
    },
)

VIBE_AUTHOR_RE = re.compile(
    r"^\*\*(?:\[(?P<linked_name>[^]]+)\]\((?P<github>https://github\.com/[^)]+)\)|(?P<plain_name>[^*]+))\*\*\s*$"
)
MARKDOWN_LINK_RE = re.compile(r"\[([^]]+)]\((https?://[^)]+)\)")
AUTHOR_CITY_RE = re.compile(r"^(?P<name>.+?)[(（](?P<city>[^()（）]+)[)）]$")
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"ref", "source", "from"}


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "indie-explorer-catalog/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def canonical_url(url: str) -> str:
    """Return a stable URL key for cross-repository deduplication."""
    parsed = urlsplit(normalize_url(url))
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parsed.path).rstrip("/").lower()
    query = urlencode(
        sorted(
            (name, value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if name.lower() not in TRACKING_QUERY_NAMES
            and not name.lower().startswith(TRACKING_QUERY_PREFIXES)
        )
    )
    return f"{host}{path}" + (f"?{query}" if query else "")


def strip_markdown(value: str) -> str:
    value = MARKDOWN_LINK_RE.sub(r"\1", value)
    value = value.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


def split_author_city(value: str) -> tuple[str, str | None]:
    match = AUTHOR_CITY_RE.match(value.strip())
    if not match:
        return value.strip(), None
    return match.group("name").strip(), match.group("city").strip()


def parse_vibe_readme(text: str) -> list[dict[str, object]]:
    projects: list[dict[str, object]] = []
    current_author: dict[str, object] | None = None
    in_code_fence = False

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        author_match = VIBE_AUTHOR_RE.match(line.strip())
        if author_match:
            name = author_match.group("linked_name") or author_match.group("plain_name")
            current_author = {
                "author": name.strip(),
                "city": None,
                "github": author_match.group("github"),
                "blog": None,
                "website": None,
            }
            continue

        if current_author is None:
            continue
        product = parse_product_line(line, current_author)
        if product is not None:
            projects.append(product)

    return projects


def parse_curated_table(text: str) -> list[dict[str, object]]:
    projects: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if len(cells) != 5:
            continue
        category, author_label, name_label, link_cell, description = cells
        link_match = re.fullmatch(r"\[访问]\((https?://[^)]+)\)", link_cell)
        if not link_match:
            continue

        author, city = split_author_city(strip_markdown(author_label))
        url = normalize_url(link_match.group(1))
        parsed_url = urlsplit(url)
        github = None
        if parsed_url.hostname == "github.com":
            owner = parsed_url.path.strip("/").split("/", 1)[0]
            if owner:
                github = f"https://github.com/{owner}"

        projects.append(
            {
                "author": author,
                "city": city,
                "github": github,
                "blog": None,
                "website": None,
                "name": strip_markdown(name_label),
                "url": url,
                "description": strip_markdown(description),
                "status": "online",
                "more_info": None,
                "category": strip_markdown(category),
            }
        )
    return projects


PARSERS: dict[str, Callable[[str], list[dict[str, object]]]] = {
    "cid": parse_readme,
    "vibe": parse_vibe_readme,
    "curated_table": parse_curated_table,
}


def merge_catalog(
    batches: list[tuple[dict[str, str], list[dict[str, object]]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    projects: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    seen: set[str] = set()

    for source_index, (source, records) in enumerate(batches):
        contributed = 0
        duplicates = 0
        prior_source_keys = set(seen)
        batch_keys: set[str] = set()
        for record in records:
            key = canonical_url(str(record["url"]))
            duplicate_in_batch = source_index > 0 and key in batch_keys
            if not key or key in prior_source_keys or duplicate_in_batch:
                duplicates += 1
                continue
            batch_keys.add(key)
            projects.append(
                {
                    **record,
                    "source": source["id"],
                    "source_url": source["url"],
                }
            )
            contributed += 1

        seen.update(batch_keys)

        sources.append(
            {
                "id": source["id"],
                "name": source["name"],
                "url": source["url"],
                "license": source["license"],
                "parsed_count": len(records),
                "contributed_count": contributed,
                "duplicate_count": duplicates,
            }
        )

    return projects, sources


def build_catalog(
    loader: Callable[[str], str] = fetch_text,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    batches = []
    for source in SOURCES:
        text = loader(source["raw_url"])
        records = PARSERS[source["parser"]](text)
        batches.append((source, records))
    return merge_catalog(batches)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the multi-source project catalog")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/projects.json"),
        help="project JSON output path",
    )
    parser.add_argument(
        "--sources-output",
        type=Path,
        default=Path("data/sources.json"),
        help="source metadata JSON output path",
    )
    args = parser.parse_args()

    projects, sources = build_catalog()
    write_json(args.output, projects)
    write_json(args.sources_output, sources)
    print(f"Collected {len(projects)} projects from {len(sources)} repositories")
    for source in sources:
        print(
            f"- {source['id']}: {source['contributed_count']} added, "
            f"{source['duplicate_count']} duplicates"
        )


if __name__ == "__main__":
    main()
