"""
build_llms_txt.py

Generates llms.txt and llms-full.txt from archived articles in content/archive/.
Run this after every `npx quartz build`:

    npx quartz build && python build_llms_txt.py

Output:
    public/llms.txt       — index of all archived articles (LLM discovery file)
    public/llms-full.txt  — full text of all archived articles concatenated
"""

import os
import re
from pathlib import Path
from datetime import datetime, timezone

ARCHIVE_DIR = Path(__file__).parent / "content" / "archive"
PUBLIC_DIR  = Path(__file__).parent / "public"
BASE_URL    = "https://thenewworldgrid.com"

def parse_frontmatter(text):
    """Extract YAML frontmatter fields (title, date, description) from markdown."""
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
            meta[key.strip().lower()] = val.strip().strip('"')
    return meta, body

def slug_to_title(stem):
    """Convert filename stem to a readable title if no frontmatter title."""
    return stem.replace("-", " ").replace("_", " ").title()

def build():
    articles = []

    for path in sorted(ARCHIVE_DIR.glob("*.md"), reverse=True):
        raw  = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)

        title       = meta.get("title") or slug_to_title(path.stem)
        date        = meta.get("date")  or ""
        description = meta.get("description") or ""

        articles.append({
            "path":        path,
            "stem":        path.stem,
            "title":       title,
            "date":        date,
            "description": description,
            "body":        body,
            "raw":         raw,
        })

    if not articles:
        print("No archived articles found in content/archive/ — nothing to write.")
        return

    PUBLIC_DIR.mkdir(exist_ok=True)

    # --- llms.txt (index) ---
    lines = [
        "# New World Grid",
        "> Intelligence synthesis covering energy acceleration, geopolitical shifts, and shadow economy metrics.",
        "",
        "Daily briefings and weekly long-form analysis. Active pages are at thenewworldgrid.com.",
        "The following are archived editions, retained for AI/LLM context.",
        "",
        "## Archived Editions",
        "",
    ]
    for a in articles:
        date_prefix = f"{a['date']}: " if a["date"] else ""
        desc_suffix = f" — {a['description']}" if a["description"] else ""
        lines.append(f"- [{date_prefix}{a['title']}]({BASE_URL}/llms-full.txt){desc_suffix}")

    lines += [
        "",
        "## Full Archive",
        "",
        f"- [All archived articles (full text)]({BASE_URL}/llms-full.txt)",
    ]

    llms_txt = PUBLIC_DIR / "llms.txt"
    llms_txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {llms_txt}  ({len(articles)} articles)")

    # --- llms-full.txt (all content concatenated) ---
    sections = [
        "# New World Grid — Full Article Archive",
        f"> Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | {len(articles)} editions",
        "",
        "This file contains the complete text of archived editions of The New World Grid.",
        "Active pages: thenewworldgrid.com",
        "",
        "---",
        "",
    ]
    for a in articles:
        sections.append(f"## {a['title']}")
        if a["date"]:
            sections.append(f"*{a['date']}*")
        sections.append("")
        sections.append(a["body"].strip())
        sections.append("")
        sections.append("---")
        sections.append("")

    llms_full = PUBLIC_DIR / "llms-full.txt"
    llms_full.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {llms_full}")

if __name__ == "__main__":
    build()
