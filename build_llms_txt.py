"""
build_llms_txt.py

Generates standard llms.txt and llms-full.txt for AI crawlers and LLM search engines.
Runs recursively across all 4 topic archives and live editions.

Outputs:
    quartz/static/llms.txt       — Structured index for AI search agents (Perplexity, SearchGPT, Claude, Gemini)
    quartz/static/llms-full.txt  — Full concatenated text of intelligence archives
    public/llms.txt              — Built public output
    public/llms-full.txt         — Built public full-text output
"""

import os
import re
from pathlib import Path
from datetime import datetime, timezone

CONTENT_DIR = Path(__file__).parent / "content"
ARCHIVE_DIR = CONTENT_DIR / "archive"
STATIC_DIR  = Path(__file__).parent / "quartz" / "static"
PUBLIC_DIR  = Path(__file__).parent / "public"
BASE_URL    = "https://thenewworldgrid.com"

TOPIC_META = {
    "predictive": {
        "name": "Predictive News",
        "author": "ORACLE",
        "description": "Anticipatory global intelligence mapping geopolitical friction, supply chain risks, and defense vectors."
    },
    "optimism": {
        "name": "Daily Optimism",
        "author": "AURORA",
        "description": "High-signal tracking of compounding breakthroughs in science, quantum computing, and clean energy."
    },
    "grid": {
        "name": "State of the Grid",
        "author": "MERIDIAN",
        "description": "Physical energy network telemetry, ERCOT grid capacity, BESS storage buildouts, and geomagnetic flux."
    },
    "frontier": {
        "name": "Final Frontier",
        "author": "ARC",
        "description": "The commercial convergence of the electric vehicle transition, mega-charging grids, and orbital economy."
    }
}

def parse_frontmatter(text):
    """Extract YAML frontmatter fields from markdown."""
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("---", 3)
    if end == -1:
        return meta, text
    front = text[3:end]
    body  = text[end + 3:].lstrip("\n")
    for line in front.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip().strip('"\'')
    return meta, body

def slug_to_title(stem):
    """Convert filename stem to a readable title."""
    return stem.replace("-", " ").replace("_", " ").title()

def build():
    by_topic = {"predictive": [], "optimism": [], "grid": [], "frontier": []}
    all_articles = []

    for path in sorted(ARCHIVE_DIR.rglob("*.md"), reverse=True):
        if path.name == "index.md":
            continue

        raw = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)

        topic = path.parent.name
        if topic not in by_topic:
            topic = "predictive"

        title = meta.get("title") or slug_to_title(path.stem)
        if ":" in title:
            title = title.split(":", 1)[1].strip()

        date = meta.get("date") or ""
        description = meta.get("description") or ""

        # Clean HTML/iframes from body for pure LLM consumption
        clean_body = re.sub(r'<iframe.*?>.*?</iframe>', '', body, flags=re.DOTALL)
        clean_body = re.sub(r'<[^>]+>', ' ', clean_body)
        clean_body = re.sub(r'<!--.*?-->', '', clean_body, flags=re.DOTALL).strip()

        rel_url = f"{BASE_URL}/archive/{topic}/{path.stem}"

        item = {
            "path": path,
            "topic": topic,
            "stem": path.stem,
            "title": title,
            "date": date,
            "description": description,
            "body": clean_body,
            "url": rel_url
        }

        by_topic[topic].append(item)
        all_articles.append(item)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    # --- llms.txt (Standard Agent Discovery File) ---
    lines = [
        "# The New World Grid",
        "> Autonomous Daily Intelligence Synthesis covering Energy Substrate, Geopolitics, Compounding Breakthroughs, and Orbital Transition.",
        "",
        "The New World Grid (thenewworldgrid.com) operates four specialized autonomous intelligence systems publishing daily briefings and continuous signal monitoring.",
        "",
        "## Core Intelligence Systems & Canonical Endpoints",
        "",
        f"- [State of the Grid (MERIDIAN)]({BASE_URL}/State-of-the-Grid): Physical energy infrastructure, ERCOT telemetry, BESS battery storage, data center power, and geomagnetic solar flux.",
        f"- [Predictive News (ORACLE)]({BASE_URL}/Predictive-News): Anticipatory global intelligence mapping geopolitical flashpoints, supply chains, and sovereign friction.",
        f"- [Daily Optimism (AURORA)]({BASE_URL}/Optimism): Compounding technical breakthroughs in science, quantum inference, clean energy, and materials.",
        f"- [Final Frontier (ARC)]({BASE_URL}/Final-Frontier): EV transport transition, mega-charging networks, battery chemistry, and orbital infrastructure.",
        "",
        "## Intelligence Archives by Domain",
        ""
    ]

    for topic_key, info in TOPIC_META.items():
        topic_items = by_topic.get(topic_key, [])
        lines.append(f"### {info['name']} ({info['author']})")
        lines.append(f"> {info['description']}")
        lines.append("")
        for a in topic_items[:15]:
            date_str = f"{a['date']}: " if a['date'] else ""
            desc_str = f" — {a['description']}" if a['description'] else ""
            lines.append(f"- [{date_str}{a['title']}]({a['url']}){desc_str}")
        lines.append("")

    lines += [
        "## Full Text Archive",
        "",
        f"- [Complete Historical Intelligence Archive (Full Text)]({BASE_URL}/llms-full.txt)"
    ]

    llms_content = "\n".join(lines)
    (STATIC_DIR / "llms.txt").write_text(llms_content, encoding="utf-8")
    (PUBLIC_DIR / "llms.txt").write_text(llms_content, encoding="utf-8")
    print(f"[+] Wrote llms.txt ({len(all_articles)} archived editions across 4 topics)")

    # --- llms-full.txt (Full Text Document) ---
    sections = [
        "# The New World Grid — Complete Intelligence Archive",
        f"> Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | {len(all_articles)} total editions",
        "",
        "This file contains the complete, unedited full text of all daily intelligence briefings published by The New World Grid.",
        "Canonical web pages: https://thenewworldgrid.com",
        "",
        "---",
        ""
    ]

    for a in all_articles:
        topic_title = TOPIC_META.get(a['topic'], {}).get('name', a['topic'])
        sections.append(f"## [{topic_title}] {a['title']}")
        if a['date']:
            sections.append(f"**Date:** {a['date']} | **Author:** {TOPIC_META.get(a['topic'], {}).get('author', 'GRID')} | **URL:** {a['url']}")
        sections.append("")
        sections.append(a['body'])
        sections.append("")
        sections.append("---")
        sections.append("")

    llms_full_content = "\n".join(sections)
    (STATIC_DIR / "llms-full.txt").write_text(llms_full_content, encoding="utf-8")
    (PUBLIC_DIR / "llms-full.txt").write_text(llms_full_content, encoding="utf-8")
    print(f"[+] Wrote llms-full.txt ({len(all_articles)} articles, {len(llms_full_content):,} bytes)")

if __name__ == "__main__":
    build()

