"""Parse the product entries in chinese-independent-developer README files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


STATUS_NAMES = {
    "white_check_mark": "online",
    "clock8": "developing",
    "x": "closed",
}

HEADER_RE = re.compile(r"^####\s+(.+?)\s*$")
PRODUCT_RE = re.compile(
    r"^\*\s+:(?P<status>white_check_mark|clock8|x):\s+"
    r"\[(?P<name>[^]]+)\]\(\s*(?P<url>[^)]+?)\s*\)"
    r"(?P<tail>.*)$"
)
LINK_RE = re.compile(r"\[([^]]+)\]\(\s*(https?://[^)]+?)\s*\)")
CITY_RE = re.compile(r"^(?P<name>.+?)[(（](?P<city>[^()（）]+)[)）]\s*(?:-\s*)?$")
MORE_INFO_RE = re.compile(r"\s+-\s+\[更多介绍\]\((https?://[^)]+)\)\s*$")


def normalize_url(url: str) -> str:
    """Make the common protocol omissions in old entries usable as URLs."""
    url = url.strip()
    if url.startswith("https:") and not url.startswith("https://"):
        return "https://" + url[len("https:") :].lstrip("/")
    if url.startswith("http:") and not url.startswith("http://"):
        return "http://" + url[len("http:") :].lstrip("/")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        return "https://" + url
    return url


def parse_author_header(line: str) -> dict[str, object] | None:
    """Parse a header such as ``#### Name(Shanghai) - [Github](...)``."""
    match = HEADER_RE.match(line)
    if not match:
        return None

    header = match.group(1)
    links = {label.lower(): url for label, url in LINK_RE.findall(header)}
    author_part = LINK_RE.sub("", header).strip()
    author_part = re.sub(r"(?:\s*[-,，]\s*)+$", "", author_part).strip()
    city_match = CITY_RE.match(author_part)
    if city_match:
        author = city_match.group("name").strip()
        city_candidate = city_match.group("city").strip()
        city = None if re.search(r"[./?=]", city_candidate) else city_candidate
    else:
        author = author_part.strip()
        city = None

    if not author:
        github_url = links.get("github")
        author = github_url.rstrip("/").rsplit("/", 1)[-1] if github_url else "未署名"
    return {
        "author": author,
        "city": city,
        "github": links.get("github"),
        "blog": links.get("博客") or links.get("blog"),
        "website": links.get("网站"),
    }


def parse_product_line(line: str, author: dict[str, object]) -> dict[str, object] | None:
    """Parse one product line and merge in the current author metadata."""
    match = PRODUCT_RE.match(line)
    if not match:
        return None

    description = match.group("tail").strip()
    description = re.sub(r"^(?:[：:]|，|,|-)\s*", "", description)
    more_info_match = MORE_INFO_RE.search(description)
    more_info = more_info_match.group(1) if more_info_match else None
    if more_info_match:
        description = description[: more_info_match.start()].rstrip()

    return {
        "author": author["author"],
        "city": author["city"],
        "github": author["github"],
        "blog": author["blog"],
        "website": author["website"],
        "name": match.group("name").strip(),
        "url": normalize_url(match.group("url")),
        "description": description,
        "status": STATUS_NAMES[match.group("status")],
        "more_info": more_info,
    }


def parse_readme(text: str) -> list[dict[str, object]]:
    """Return all product records found in a README string."""
    projects: list[dict[str, object]] = []
    current_author: dict[str, object] | None = None

    for line in text.splitlines():
        if line.startswith("#### "):
            current_author = parse_author_header(line)
            continue
        if current_author is None:
            continue
        product = parse_product_line(line, current_author)
        if product is not None:
            projects.append(product)

    return projects


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse product entries from a Markdown README")
    parser.add_argument("input", type=Path, help="input README path")
    parser.add_argument("output", type=Path, help="output JSON path")
    args = parser.parse_args()

    projects = parse_readme(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(projects, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Parsed {len(projects)} projects into {args.output}")


if __name__ == "__main__":
    main()
