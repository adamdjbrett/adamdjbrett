#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import html
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone


README = "README.md"
START = "<!-- FEED:START -->"
END = "<!-- FEED:END -->"
FEEDS = [
    "https://www.adamdjbrett.com/feed/feed.xml",
    "https://lemma.pub/did:plc:3vmq5usrh3yvhbrrzf4ymo23/pub/3mpfn7klatsip/feed.xml",
]


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    published: datetime
    source: str


def text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return html.unescape(node.text.strip())


def child(node: ET.Element, name: str) -> ET.Element | None:
    for item in node:
        if item.tag.rsplit("}", 1)[-1] == name:
            return item
    return None


def children(node: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in node if item.tag.rsplit("}", 1)[-1] == name]


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def markdown_link_text(value: str) -> str:
    return re.sub(r"[\[\]\n\r]+", " ", value).strip()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "adamdjbrett-readme-feed-updater/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def parse_feed(url: str) -> list[Entry]:
    try:
        root = ET.fromstring(fetch(url))
    except urllib.error.HTTPError as error:
        print(f"Skipping feed {url}: HTTP {error.code}", file=sys.stderr)
        return []
    except urllib.error.URLError as error:
        print(f"Skipping feed {url}: {error.reason}", file=sys.stderr)
        return []

    source = text(child(child(root, "channel") or root, "title")) or url

    items = children(child(root, "channel") or root, "item")
    if not items:
        items = children(root, "entry")

    entries = []
    for item in items:
        title = text(child(item, "title"))
        link = text(child(item, "link"))
        if not link:
            link_node = child(item, "link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""

        published = text(child(item, "pubDate")) or text(child(item, "published")) or text(child(item, "updated"))
        if title and link:
            entries.append(Entry(title=title, url=link, published=parse_date(published), source=source))

    return entries


def render(entries: list[Entry]) -> str:
    if not entries:
        return "_No recent posts found._"

    lines = []
    for entry in entries[:5]:
        date = entry.published.astimezone(timezone.utc).strftime("%Y-%m-%d")
        title = markdown_link_text(entry.title)
        source = markdown_link_text(entry.source)
        lines.append(f"- {date}: [{title}]({entry.url}) - {source}")
    return "\n".join(lines)


def main() -> int:
    entries = []
    for url in FEEDS:
        entries.extend(parse_feed(url))

    entries.sort(key=lambda entry: entry.published, reverse=True)
    replacement = f"{START}\n{render(entries)}\n{END}"

    with open(README, "r", encoding="utf-8") as file:
        readme = file.read()

    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
    if not pattern.search(readme):
        print(f"Missing {START}/{END} markers in {README}", file=sys.stderr)
        return 1

    updated = pattern.sub(replacement, readme)
    with open(README, "w", encoding="utf-8") as file:
        file.write(updated)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
