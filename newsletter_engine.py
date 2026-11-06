#!/usr/bin/env python3
r"""
==============================================================================
[aeOS:Home:Newsletter]
Script / Service: newsletter_engine.py
Path: C:\Users\bertb\aeOS\home\new_world_grid\newsletter_engine.py
Role & Mission: Zero-API Open-Source Newsletter Engine for thenewworldgrid.com.
                1. Strict Data vs. LLM Text Isolation (NewsletterBuilder):
                   - LLM prose is strictly sanitized/HTML-escaped and confined to
                     dedicated TextSectionBlock slots.
                   - Metrics (MetricStripBlock), Tables (DataTableBlock), and
                     Graphs (ChartImageBlock -> Matplotlib CID PNG) are rendered
                     deterministically by code so HTML/table layout can never be
                     corrupted by LLM text generation.
                2. Dual Subscriber Capture & Sync (SubscriberManager):
                   - Syncs 24/7 website form signups from Google Sheet ('Subscribers' tab)
                     into local SQLite (C:\Users\bertb\new-world-grid\data\subscribers.db).
                   - Polls thenewworldgrid@gmail.com via IMAP SSL (imap.gmail.com:993)
                     for emailed signups (e.g. anything@thenewworldgrid.com) and
                     'unsubscribe' replies.
                   - Dispatches immediate Welcome Emails via SMTP SSL (smtp.gmail.com:465)
                     and sends the Weekly Sunday Recap every Sunday at 7:30 PM EST (19:30).
Operating Schedule: Sunday 19:30 EST Weekly Dispatch + Continuous 10-Min Subscriber Sync
Node Affinity: Home-Laptop
Invariants & Guardrails:
  - Zero third-party email APIs (pure Python smtplib, imaplib, email.message, sqlite3, matplotlib)
  - Total isolation between LLM text strings and HTML table/chart structures
  - Double-send lock via editions_log table (one edition per ISO week)
Shared Contracts:
  - SQLite DB: C:\Users\bertb\new-world-grid\data\subscribers.db
  - Google Sheet Tab: Subscribers
  - Preview Output: C:\Users\bertb\new-world-grid\data\preview_weekly_recap.html
==============================================================================
"""

import argparse
import contextlib
import dataclasses
import datetime
import email
import email.policy
import html
import imaplib
import io
import json
import os
import re
import smtplib
import sqlite3
import ssl
import sys
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Resolve paths & canonical config
THIS_DIR = Path(__file__).resolve().parent
AEOS_ROOT = THIS_DIR.parent.parent if (THIS_DIR.parent.parent / "shared" / "aeos_config.py").exists() else Path(r"C:\Users\bertb\aeOS")
SYSTEMS_DIR = Path(r"C:\Users\bertb\gemini\intelligence\systems")
GEMINI_DIR = Path(r"C:\Users\bertb\gemini")
QUARTZ_REPO_DIR = Path(r"C:\Users\bertb\new-world-grid")
DATA_DIR = QUARTZ_REPO_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

for p in [str(AEOS_ROOT / "shared"), str(SYSTEMS_DIR), str(GEMINI_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from aeos_config import (
        APPS_SCRIPT_URL,
        GOOGLE_SHEET_ID,
        NWG_GMAIL_APP_PASSWORD,
        NWG_GMAIL_USER,
        NWG_SENDER_NAME,
        NWG_SUBSCRIBERS_DB,
        NWG_SUBSCRIBERS_TAB,
        TELEGRAM_CHAT_ID,
        TELEGRAM_TOKEN,
    )
except ImportError:
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "1Sh_X2nspAMNZFoWqtuePDoHVkWUr9Dha_0HUlfxmbDY")
    APPS_SCRIPT_URL = os.environ.get(
        "APPS_SCRIPT_URL",
        "https://script.google.com/macros/s/AKfycbxKqwM1gUfAdR_-ZZBxtQkDG1yyDYcRwcM9TT6n-MojsgV2muorp9tHM2BgvHsnKZyJ/exec",
    )
    NWG_GMAIL_USER = os.environ.get("NWG_GMAIL_USER", "thenewworldgrid@gmail.com")
    NWG_GMAIL_APP_PASSWORD = os.environ.get("NWG_GMAIL_APP_PASSWORD", "")
    NWG_SENDER_NAME = os.environ.get("NWG_SENDER_NAME", "The New World Grid")
    NWG_SUBSCRIBERS_TAB = os.environ.get("NWG_SUBSCRIBERS_TAB", "Subscribers")
    NWG_SUBSCRIBERS_DB = DATA_DIR / "subscribers.db"

try:
    import obsidian_bridge
except ImportError:
    obsidian_bridge = None

import requests

SERVICE_ACCOUNT_FILE = GEMINI_DIR / "service_account.json"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SITE_URL = "https://thenewworldgrid.com"


# ==============================================================================
# 1. STRICT DATA vs. LLM TEXT ISOLATION & HYGIENE PRIMITIVES
# ==============================================================================

_HTML_TAG_STRIP_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_EMAIL_VALID_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def normalize_email(raw_email: str) -> str:
    """Extracts and validates a lowercase email address."""
    if not raw_email:
        return ""
    _, addr = parseaddr(raw_email.strip())
    candidate = (addr or raw_email).strip().lower()
    if _EMAIL_VALID_RE.match(candidate):
        return candidate
    return ""


def sanitize_llm_prose(raw_text: str) -> List[str]:
    """
    Strictly sanitizes LLM-generated or written prose so it can NEVER corrupt
    email HTML or leak into table/data structures.
    - Strips any accidental HTML tags (<script>, <div>, <table>, <p>, etc.)
    - Strips markdown code fences
    - Splits paragraphs cleanly on blank lines
    - Escapes all HTML entities (&, <, >, ", ') via html.escape()
    """
    if not raw_text:
        return []
    text = str(raw_text).replace("\r\n", "\n").replace("\r", "\n")
    # Remove markdown code fences if LLM emitted them
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    # Strip any raw HTML tags so LLM output cannot inject DOM elements
    text = _HTML_TAG_STRIP_RE.sub("", text)
    paragraphs: List[str] = []
    for raw_para in re.split(r"\n\s*\n", text):
        cleaned = " ".join(line.strip() for line in raw_para.splitlines() if line.strip())
        if cleaned:
            paragraphs.append(html.escape(cleaned, quote=True))
    return paragraphs


def sanitize_cell_value(value: Any) -> str:
    """Strictly sanitizes a single deterministic table/metric cell value."""
    if value is None:
        return "—"
    raw = str(value).strip()
    if not raw:
        return "—"
    raw = _HTML_TAG_STRIP_RE.sub("", raw)
    return html.escape(raw, quote=True)


def _is_numeric_like(value: Any) -> bool:
    """Detects numeric, currency, delta, or percentage values for tabular right-alignment."""
    if isinstance(value, (int, float)):
        return True
    s = str(value).strip()
    return bool(re.match(r"^[+\-$€£¥~]?\s*\d[\d,._/%+\-A-Za-z]*$", s))


@dataclasses.dataclass
class InlineChartAttachment:
    """Represents an in-memory PNG chart attached via MIME Content-ID (cid:)."""
    chart_id: str
    filename: str
    png_bytes: bytes
    alt_text: str


@dataclasses.dataclass
class TextSectionBlock:
    """
    ISOLATED PROSE SLOT:
    Holds LLM-written or human-written narrative text ONLY.
    All text is strictly HTML-escaped and rendered in editorial serif paragraphs.
    """
    section_id: str
    heading: str
    paragraphs: List[str] = dataclasses.field(default_factory=list)
    kicker: Optional[str] = None
    callout: Optional[str] = None
    is_placeholder: bool = False

    def render_html(self) -> str:
        safe_heading = sanitize_cell_value(self.heading)
        safe_kicker = sanitize_cell_value(self.kicker) if self.kicker else ""
        safe_paras: List[str] = []
        for p in self.paragraphs:
            safe_paras.extend(sanitize_llm_prose(p))

        kicker_html = (
            f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
            f'font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#10b981;'
            f'margin:0 0 6px 0;">{safe_kicker}</div>'
            if safe_kicker
            else ""
        )

        if self.is_placeholder and not safe_paras:
            body_html = (
                '<div style="padding:16px;border:1px dashed #cbd5e1;background-color:#f8fafc;'
                'font-family:\'JetBrains Mono\',Consolas,monospace;font-size:12px;color:#64748b;'
                'line-height:1.6;">'
                f'[PROSE SLOT: {html.escape(self.section_id)} — Isolated LLM/Written Narrative Container. '
                'Awaiting weekly editorial context.]'
                '</div>'
            )
        else:
            p_tags = [
                f'<p style="font-family:Georgia,\'Libre Baskerville\',serif;font-size:16px;'
                f'line-height:1.72;color:#1e293b;margin:0 0 14px 0;">{para}</p>'
                for para in safe_paras
            ]
            body_html = "\n".join(p_tags)

        callout_html = ""
        if self.callout:
            safe_callout = " ".join(sanitize_llm_prose(self.callout))
            if safe_callout:
                callout_html = (
                    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                    'style="margin:12px 0 4px 0;background-color:#f8fafc;border-left:3px solid #0f172a;">'
                    '<tr><td style="padding:12px 16px;font-family:Georgia,\'Libre Baskerville\',serif;'
                    f'font-size:15px;line-height:1.6;color:#0f172a;font-style:italic;">{safe_callout}</td></tr>'
                    '</table>'
                )

        return (
            f'<!-- START ISOLATED PROSE BLOCK: {html.escape(self.section_id)} -->\n'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:0 0 24px 0;border-collapse:collapse;">'
            '<tr><td style="padding:20px 24px;background-color:#ffffff;border:1px solid #e2e8f0;">'
            f'{kicker_html}'
            f'<h2 style="font-family:Georgia,\'Libre Baskerville\',serif;font-size:20px;'
            f'font-weight:700;color:#0f172a;margin:0 0 14px 0;line-height:1.3;">{safe_heading}</h2>'
            f'{body_html}'
            f'{callout_html}'
            '</td></tr></table>\n'
            f'<!-- END ISOLATED PROSE BLOCK: {html.escape(self.section_id)} -->'
        )

    def render_text(self) -> str:
        lines = []
        if self.kicker:
            lines.append(f"[{self.kicker.upper()}]")
        lines.append(self.heading.upper())
        lines.append("-" * len(self.heading))
        if self.is_placeholder and not self.paragraphs:
            lines.append(f"[Prose Slot: {self.section_id} — Awaiting weekly editorial context]")
        else:
            for p in self.paragraphs:
                for clean_p in sanitize_llm_prose(p):
                    lines.append(html.unescape(clean_p))
                    lines.append("")
        if self.callout:
            lines.append(f"> {self.callout.strip()}")
        return "\n".join(lines).strip()


@dataclasses.dataclass
class MetricItem:
    """Single KPI metric item inside a deterministic MetricStripBlock."""
    label: str
    value: str
    delta: str = ""
    trend: str = "neutral"  # "up", "down", "neutral"


@dataclasses.dataclass
class MetricStripBlock:
    """
    ISOLATED DATA KPI STRIP:
    Renders structured key performance indicators in a deterministic HTML table.
    Zero LLM prose is permitted inside this block.
    """
    block_id: str
    title: str
    metrics: List[MetricItem] = dataclasses.field(default_factory=list)
    is_placeholder: bool = False

    def render_html(self) -> str:
        safe_title = sanitize_cell_value(self.title)
        if self.is_placeholder and not self.metrics:
            inner_html = (
                '<div style="padding:14px;border:1px dashed #cbd5e1;background-color:#f8fafc;'
                'font-family:\'JetBrains Mono\',Consolas,monospace;font-size:12px;color:#64748b;">'
                f'[DATA KPI STRIP SLOT: {html.escape(self.block_id)} — Deterministic Metric Cards Container]'
                '</div>'
            )
        else:
            cols = max(1, len(self.metrics))
            width_pct = int(100 / cols)
            cells = []
            for idx, m in enumerate(self.metrics):
                lbl = sanitize_cell_value(m.label)
                val = sanitize_cell_value(m.value)
                dlt = sanitize_cell_value(m.delta) if m.delta else ""
                if m.trend == "up":
                    delta_color = "#15803d"
                    delta_bg = "#dcfce7"
                elif m.trend == "down":
                    delta_color = "#b91c1c"
                    delta_bg = "#fee2e2"
                else:
                    delta_color = "#475569"
                    delta_bg = "#f1f5f9"

                border_right = "border-right:1px solid #e2e8f0;" if idx < cols - 1 else ""
                delta_badge = (
                    f'<div style="margin-top:6px;"><span style="display:inline-block;padding:2px 6px;'
                    f'background-color:{delta_bg};color:{delta_color};font-family:\'JetBrains Mono\',Consolas,monospace;'
                    f'font-size:11px;font-weight:700;">{dlt}</span></div>'
                    if dlt and dlt != "—"
                    else ""
                )
                cells.append(
                    f'<td width="{width_pct}%" valign="top" style="padding:14px 12px;{border_right}text-align:left;">'
                    f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:10px;'
                    f'font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;'
                    f'margin-bottom:6px;">{lbl}</div>'
                    f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:20px;'
                    f'font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;">{val}</div>'
                    f'{delta_badge}'
                    f'</td>'
                )
            inner_html = (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'style="border-collapse:collapse;background-color:#f8fafc;border:1px solid #e2e8f0;">'
                f'<tr>{"".join(cells)}</tr></table>'
            )

        return (
            f'<!-- START ISOLATED METRIC STRIP BLOCK: {html.escape(self.block_id)} -->\n'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:0 0 24px 0;border-collapse:collapse;">'
            '<tr><td style="padding:18px 24px;background-color:#ffffff;border:1px solid #e2e8f0;">'
            f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
            f'font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#0f172a;'
            f'margin:0 0 12px 0;">{safe_title}</div>'
            f'{inner_html}'
            '</td></tr></table>\n'
            f'<!-- END ISOLATED METRIC STRIP BLOCK: {html.escape(self.block_id)} -->'
        )

    def render_text(self) -> str:
        lines = [f"[{self.title.upper()}]"]
        if self.is_placeholder and not self.metrics:
            lines.append(f"  [KPI Strip Slot: {self.block_id} — Awaiting weekly metric feed]")
        else:
            for m in self.metrics:
                d = f" ({m.delta})" if m.delta else ""
                lines.append(f"  • {m.label}: {m.value}{d}")
        return "\n".join(lines)


@dataclasses.dataclass
class DataTableBlock:
    """
    ISOLATED DETERMINISTIC DATA TABLE:
    Builds a strict, email-client-safe <table> from structured Python columns & rows.
    Every cell is sanitized independently; numeric columns are automatically right-aligned
    with monospace tabular numerals.
    """
    table_id: str
    title: str
    columns: List[str] = dataclasses.field(default_factory=list)
    rows: List[Sequence[Any]] = dataclasses.field(default_factory=list)
    alignments: Optional[List[str]] = None
    subtitle: Optional[str] = None
    footnote: Optional[str] = None
    is_placeholder: bool = False

    def _resolve_alignments(self) -> List[str]:
        if self.alignments and len(self.alignments) == len(self.columns):
            return [a if a in ("left", "right", "center") else "left" for a in self.alignments]
        resolved = []
        for col_idx in range(len(self.columns)):
            if col_idx == 0:
                resolved.append("left")
                continue
            sample_vals = [r[col_idx] for r in self.rows if col_idx < len(r) and r[col_idx] not in (None, "")]
            if sample_vals and all(_is_numeric_like(v) for v in sample_vals):
                resolved.append("right")
            else:
                resolved.append("left")
        return resolved

    def render_html(self) -> str:
        safe_title = sanitize_cell_value(self.title)
        safe_sub = sanitize_cell_value(self.subtitle) if self.subtitle else ""
        sub_html = (
            f'<div style="font-family:\'Source Sans Pro\',Arial,sans-serif;font-size:13px;'
            f'color:#64748b;margin:0 0 12px 0;">{safe_sub}</div>'
            if safe_sub
            else ""
        )

        if self.is_placeholder and not self.rows:
            table_html = (
                '<div style="padding:16px;border:1px dashed #cbd5e1;background-color:#f8fafc;'
                'font-family:\'JetBrains Mono\',Consolas,monospace;font-size:12px;color:#64748b;">'
                f'[DATA TABLE SLOT: {html.escape(self.table_id)} — Deterministic Tabular Data Container]'
                '</div>'
            )
        else:
            aligns = self._resolve_alignments()
            th_cells = []
            for idx, col in enumerate(self.columns):
                align = aligns[idx] if idx < len(aligns) else "left"
                th_cells.append(
                    f'<th align="{align}" style="padding:10px 12px;background-color:#0f172a;'
                    f'color:#f8fafc;font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
                    f'font-weight:700;text-transform:uppercase;letter-spacing:0.06em;'
                    f'text-align:{align};border-bottom:2px solid #10b981;">'
                    f'{sanitize_cell_value(col)}</th>'
                )

            tr_rows = []
            for r_idx, row in enumerate(self.rows):
                bg = "#ffffff" if r_idx % 2 == 0 else "#f8fafc"
                td_cells = []
                for c_idx in range(len(self.columns)):
                    raw_val = row[c_idx] if c_idx < len(row) else ""
                    safe_val = sanitize_cell_value(raw_val)
                    align = aligns[c_idx] if c_idx < len(aligns) else "left"
                    font_family = (
                        "'JetBrains Mono',Consolas,monospace"
                        if align == "right" or c_idx > 0
                        else "'Source Sans Pro',Arial,sans-serif"
                    )
                    font_weight = "600" if c_idx == 0 else "400"
                    td_cells.append(
                        f'<td align="{align}" style="padding:10px 12px;background-color:{bg};'
                        f'border-bottom:1px solid #e2e8f0;font-family:{font_family};'
                        f'font-size:13px;font-weight:{font_weight};color:#1e293b;'
                        f'text-align:{align};font-variant-numeric:tabular-nums;">{safe_val}</td>'
                    )
                tr_rows.append(f'<tr>{"".join(td_cells)}</tr>')

            table_html = (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'style="border-collapse:collapse;border:1px solid #cbd5e1;">'
                f'<thead><tr>{"".join(th_cells)}</tr></thead>'
                f'<tbody>{"".join(tr_rows)}</tbody>'
                '</table>'
            )

        foot_html = ""
        if self.footnote:
            safe_foot = sanitize_cell_value(self.footnote)
            foot_html = (
                f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
                f'color:#64748b;margin-top:8px;">{safe_foot}</div>'
            )

        return (
            f'<!-- START ISOLATED DATA TABLE BLOCK: {html.escape(self.table_id)} -->\n'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:0 0 24px 0;border-collapse:collapse;">'
            '<tr><td style="padding:20px 24px;background-color:#ffffff;border:1px solid #e2e8f0;">'
            f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
            f'font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#10b981;'
            f'margin:0 0 4px 0;">DATA LEDGER</div>'
            f'<h3 style="font-family:Georgia,\'Libre Baskerville\',serif;font-size:18px;'
            f'font-weight:700;color:#0f172a;margin:0 0 8px 0;">{safe_title}</h3>'
            f'{sub_html}'
            f'{table_html}'
            f'{foot_html}'
            '</td></tr></table>\n'
            f'<!-- END ISOLATED DATA TABLE BLOCK: {html.escape(self.table_id)} -->'
        )

    def render_text(self) -> str:
        lines = [f"[TABLE: {self.title.upper()}]"]
        if self.is_placeholder and not self.rows:
            lines.append(f"  [Data Table Slot: {self.table_id} — Awaiting weekly tabular dataset]")
            return "\n".join(lines)
        if self.columns:
            lines.append("  " + " | ".join(str(c) for c in self.columns))
            lines.append("  " + "-+-".join("-" * len(str(c)) for c in self.columns))
        for r in self.rows:
            lines.append("  " + " | ".join(str(x) for x in r))
        if self.footnote:
            lines.append(f"  Note: {self.footnote}")
        return "\n".join(lines)


@dataclasses.dataclass
class ChartImageBlock:
    """
    ISOLATED DETERMINISTIC CHART BLOCK:
    Renders structured series data to a high-DPI PNG image using Matplotlib (Agg)
    and embeds it as an inline MIME Content-ID (cid:) image so every email client
    displays the chart natively without JavaScript or external image trackers.
    """
    chart_id: str
    title: str
    chart_type: str = "line"  # "line", "bar", "hbar"
    labels: List[str] = dataclasses.field(default_factory=list)
    series: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    y_label: str = ""
    caption: Optional[str] = None
    png_bytes: Optional[bytes] = None
    is_placeholder: bool = False

    def compile_png(self) -> Optional[bytes]:
        if self.png_bytes:
            return self.png_bytes
        if self.is_placeholder or not self.labels or not self.series:
            return None

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        palette = ["#0f172a", "#10b981", "#2563eb", "#f59e0b", "#ef4444"]
        fig, ax = plt.subplots(figsize=(6.8, 3.4), dpi=160)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#f8fafc")

        x_indices = list(range(len(self.labels)))
        n_series = max(1, len(self.series))

        for idx, s in enumerate(self.series):
            vals = [float(v) for v in s.get("values", [])]
            s_label = str(s.get("name", f"Series {idx + 1}"))
            color = s.get("color") or palette[idx % len(palette)]

            if self.chart_type == "bar":
                bar_width = 0.72 / n_series
                offsets = [x - 0.36 + (idx + 0.5) * bar_width for x in x_indices]
                ax.bar(offsets, vals, width=bar_width * 0.9, label=s_label, color=color, zorder=3)
            elif self.chart_type == "hbar":
                bar_height = 0.72 / n_series
                offsets = [y - 0.36 + (idx + 0.5) * bar_height for y in x_indices]
                ax.barh(offsets, vals, height=bar_height * 0.9, label=s_label, color=color, zorder=3)
            else:
                ax.plot(
                    x_indices,
                    vals,
                    marker="o",
                    linewidth=2.2,
                    markersize=5,
                    label=s_label,
                    color=color,
                    zorder=4,
                )

        if self.chart_type == "hbar":
            ax.set_yticks(x_indices)
            ax.set_yticklabels(self.labels, fontsize=9, color="#334155", fontfamily="monospace")
            ax.grid(axis="x", linestyle="--", alpha=0.5, color="#cbd5e1", zorder=0)
            if self.y_label:
                ax.set_xlabel(self.y_label, fontsize=9, color="#475569", fontfamily="monospace")
        else:
            ax.set_xticks(x_indices)
            ax.set_xticklabels(self.labels, fontsize=9, color="#334155", fontfamily="monospace")
            ax.grid(axis="y", linestyle="--", alpha=0.5, color="#cbd5e1", zorder=0)
            if self.y_label:
                ax.set_ylabel(self.y_label, fontsize=9, color="#475569", fontfamily="monospace")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(colors="#475569", labelsize=8.5)

        if len(self.series) > 1:
            ax.legend(frameon=False, fontsize=8.5, loc="upper left")

        fig.tight_layout(pad=1.1)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=160, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        self.png_bytes = buf.getvalue()
        return self.png_bytes

    def get_cid(self) -> str:
        clean_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", self.chart_id)
        return f"{clean_id}@thenewworldgrid.com"

    def render_html(self) -> Tuple[str, Optional[InlineChartAttachment]]:
        safe_title = sanitize_cell_value(self.title)
        safe_caption = sanitize_cell_value(self.caption) if self.caption else ""
        png_data = self.compile_png()
        attachment: Optional[InlineChartAttachment] = None

        if png_data is None:
            visual_html = (
                '<div style="padding:20px;border:1px dashed #cbd5e1;background-color:#f8fafc;'
                'font-family:\'JetBrains Mono\',Consolas,monospace;font-size:12px;color:#64748b;'
                'text-align:center;">'
                f'[CHART TELEMETRY SLOT: {html.escape(self.chart_id)} — Deterministic Matplotlib CID PNG Container]'
                '</div>'
            )
        else:
            cid = self.get_cid()
            attachment = InlineChartAttachment(
                chart_id=cid,
                filename=f"{re.sub(r'[^a-zA-Z0-9_-]', '_', self.chart_id)}.png",
                png_bytes=png_data,
                alt_text=self.title,
            )
            visual_html = (
                f'<img src="cid:{cid}" alt="{safe_title}" width="550" '
                f'style="display:block;width:100%;max-width:550px;height:auto;border:1px solid #e2e8f0;" />'
            )

        caption_html = (
            f'<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
            f'color:#64748b;margin-top:8px;line-height:1.5;">{safe_caption}</div>'
            if safe_caption
            else ""
        )

        block_html = (
            f'<!-- START ISOLATED CHART BLOCK: {html.escape(self.chart_id)} -->\n'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:0 0 24px 0;border-collapse:collapse;">'
            '<tr><td style="padding:20px 24px;background-color:#ffffff;border:1px solid #e2e8f0;">'
            '<div style="font-family:\'JetBrains Mono\',Consolas,monospace;font-size:11px;'
            'font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#10b981;'
            'margin:0 0 4px 0;">VISUAL TELEMETRY</div>'
            f'<h3 style="font-family:Georgia,\'Libre Baskerville\',serif;font-size:18px;'
            f'font-weight:700;color:#0f172a;margin:0 0 12px 0;">{safe_title}</h3>'
            f'{visual_html}'
            f'{caption_html}'
            '</td></tr></table>\n'
            f'<!-- END ISOLATED CHART BLOCK: {html.escape(self.chart_id)} -->'
        )
        return block_html, attachment

    def render_text(self) -> str:
        lines = [f"[CHART: {self.title.upper()}]"]
        if self.is_placeholder or not self.labels or not self.series:
            lines.append(f"  [Visual Chart Slot: {self.chart_id} — Awaiting weekly telemetry series]")
        else:
            for s in self.series:
                name = s.get("name", "Series")
                pairs = ", ".join(f"{lbl}: {val}" for lbl, val in zip(self.labels, s.get("values", [])))
                lines.append(f"  • {name}: {pairs}")
        if self.caption:
            lines.append(f"  Caption: {self.caption}")
        return "\n".join(lines)


NewsletterBlock = Union[TextSectionBlock, MetricStripBlock, DataTableBlock, ChartImageBlock]


class NewsletterBuilder:
    """
    Assembles isolated Prose (TextSectionBlock) and Data (MetricStripBlock,
    DataTableBlock, ChartImageBlock) blocks into a hygienic, mobile-responsive
    HTML + Plain-Text + Inline-CID MIME email.
    """

    def __init__(
        self,
        subject: str,
        edition_label: str,
        date_label: Optional[str] = None,
        preheader: str = "Weekly Intelligence & Data Recap from The New World Grid.",
    ):
        self.subject = subject.strip()
        self.edition_label = edition_label.strip()
        self.date_label = date_label or datetime.datetime.now().strftime("%B %d, %Y")
        self.preheader = preheader.strip()
        self.blocks: List[NewsletterBlock] = []

    def add_block(self, block: NewsletterBlock) -> "NewsletterBuilder":
        if not isinstance(block, (TextSectionBlock, MetricStripBlock, DataTableBlock, ChartImageBlock)):
            raise TypeError(
                f"Data/Text Isolation Violation: Invalid block type {type(block).__name__}. "
                "Use TextSectionBlock, MetricStripBlock, DataTableBlock, or ChartImageBlock."
            )
        self.blocks.append(block)
        return self

    def render(self, unsubscribe_email: str = "") -> Tuple[str, str, List[InlineChartAttachment]]:
        """Returns (html_body, plain_text_body, inline_attachments)."""
        rendered_html_blocks: List[str] = []
        rendered_text_blocks: List[str] = []
        attachments: List[InlineChartAttachment] = []

        for block in self.blocks:
            if isinstance(block, ChartImageBlock):
                b_html, att = block.render_html()
                rendered_html_blocks.append(b_html)
                if att:
                    attachments.append(att)
            else:
                rendered_html_blocks.append(block.render_html())
            rendered_text_blocks.append(block.render_text())

        safe_edition = sanitize_cell_value(self.edition_label)
        safe_date = sanitize_cell_value(self.date_label)
        safe_subject = sanitize_cell_value(self.subject)
        safe_preheader = sanitize_cell_value(self.preheader)
        unsub_mailto = f"mailto:{NWG_GMAIL_USER}?subject=Unsubscribe"
        if unsubscribe_email:
            unsub_mailto += f"%20({urllib_quote(unsubscribe_email)})"

        html_doc = f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{safe_subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <!-- Hidden Preheader -->
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#f1f5f9;">
    {safe_preheader}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;margin:0;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;border-collapse:collapse;">
          <!-- Masthead -->
          <tr>
            <td style="padding:24px 28px;background-color:#0f172a;border-bottom:4px solid #10b981;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="left" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#10b981;">
                    {safe_edition}
                  </td>
                  <td align="right" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:11px;color:#94a3b8;">
                    {safe_date}
                  </td>
                </tr>
              </table>
              <h1 style="font-family:Georgia,'Libre Baskerville',serif;font-size:26px;font-weight:700;color:#f8fafc;margin:10px 0 4px 0;letter-spacing:-0.01em;">
                THE NEW WORLD GRID
              </h1>
              <div style="font-family:'Source Sans Pro',Arial,sans-serif;font-size:14px;color:#cbd5e1;margin:0;">
                {safe_subject}
              </div>
            </td>
          </tr>

          <!-- Spacer -->
          <tr><td style="height:20px;font-size:1px;line-height:1px;">&nbsp;</td></tr>

          <!-- Isolated Content Blocks -->
          <tr>
            <td style="padding:0;">
              {"".join(rendered_html_blocks)}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 24px;background-color:#0f172a;color:#94a3b8;font-family:'JetBrains Mono',Consolas,monospace;font-size:11px;line-height:1.6;text-align:center;">
              <div style="margin-bottom:8px;">
                <a href="{SITE_URL}" style="color:#10b981;text-decoration:none;font-weight:700;">thenewworldgrid.com</a>
                &nbsp;|&nbsp;
                <a href="{SITE_URL}/State-of-the-Grid" style="color:#cbd5e1;text-decoration:none;">State of the Grid</a>
                &nbsp;|&nbsp;
                <a href="{SITE_URL}/Predictive-News" style="color:#cbd5e1;text-decoration:none;">Predictive News</a>
                &nbsp;|&nbsp;
                <a href="{SITE_URL}/Final-Frontier" style="color:#cbd5e1;text-decoration:none;">Final Frontier</a>
              </div>
              <div>
                Dispatched every Sunday at 7:30 PM EST by The New World Grid.<br/>
                To opt out at any time, reply with <strong>UNSUBSCRIBE</strong> or <a href="{unsub_mailto}" style="color:#cbd5e1;text-decoration:underline;">click here to unsubscribe</a>.
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        plain_text = (
            f"THE NEW WORLD GRID — {self.edition_label}\n"
            f"{self.subject} ({self.date_label})\n"
            f"{'=' * 64}\n\n"
            + "\n\n".join(rendered_text_blocks)
            + f"\n\n{'=' * 64}\n"
            f"Read live on the grid: {SITE_URL}\n"
            f"To unsubscribe, reply to this email with 'UNSUBSCRIBE'.\n"
        )
        return html_doc, plain_text, attachments

    def to_email_message(
        self,
        recipient_email: str,
        sender_email: str = NWG_GMAIL_USER,
        sender_name: str = NWG_SENDER_NAME,
    ) -> EmailMessage:
        """Builds a standard RFC 5322 / MIME multipart EmailMessage with CID inline images."""
        html_body, text_body, attachments = self.render(unsubscribe_email=recipient_email)

        msg = EmailMessage()
        msg["Subject"] = self.subject
        msg["From"] = formataddr((sender_name, sender_email))
        msg["To"] = recipient_email
        msg["Reply-To"] = sender_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="thenewworldgrid.com")
        msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=Unsubscribe>"

        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        if attachments:
            html_part = msg.get_body(preferencelist=("html",))
            for att in attachments:
                cid_bracketed = f"<{att.chart_id}>"
                html_part.add_related(
                    att.png_bytes,
                    maintype="image",
                    subtype="png",
                    cid=cid_bracketed,
                    filename=att.filename,
                    disposition="inline",
                )

        return msg


def urllib_quote(val: str) -> str:
    from urllib.parse import quote
    return quote(val or "")


# ==============================================================================
# 2. TEMPLATES: EMPTY WEEKLY SUNDAY RECAP SCAFFOLD & IMMEDIATE WELCOME EMAIL
# ==============================================================================

def get_prior_week_window(ref_dt: Optional[datetime.datetime] = None) -> Tuple[str, str, str]:
    """Returns (iso_edition_id, range_label, date_label) for the Sunday weekly recap."""
    now = ref_dt or datetime.datetime.now()
    start_dt = now - datetime.timedelta(days=6)
    iso_year, iso_week, _ = now.isocalendar()
    edition_id = f"{iso_year}-W{iso_week:02d}"
    range_label = f"{start_dt.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
    date_label = now.strftime("%B %d, %Y")
    return edition_id, range_label, date_label


def build_weekly_recap_scaffold(ref_dt: Optional[datetime.datetime] = None) -> NewsletterBuilder:
    """
    Constructs the Sunday Weekly Recap Newsletter with strictly isolated Prose vs. Data slots.
    NOTE: Per user specification, the actual weekly contents are intentionally left empty
    (structured placeholder slots) until content/reporting specifications are provided.
    """
    edition_id, range_label, date_label = get_prior_week_window(ref_dt)
    builder = NewsletterBuilder(
        subject=f"The New World Grid // Weekly Briefing ({range_label})",
        edition_label=f"SUNDAY RECAP // EDITION {edition_id}",
        date_label=date_label,
        preheader=f"Weekly synthesis and telemetry recap for {range_label}.",
    )

    # 1. Isolated Written/LLM Narrative Slot (Opening Thesis)
    builder.add_block(
        TextSectionBlock(
            section_id="weekly_opening_synthesis",
            kicker="PART I // EDITORIAL SYNTHESIS",
            heading="Prior Week Signal Recap",
            paragraphs=[],
            is_placeholder=True,
        )
    )

    # 2. Isolated Deterministic KPI Metric Strip Slot
    builder.add_block(
        MetricStripBlock(
            block_id="weekly_kpi_strip",
            title="WEEKLY GRID TELEMETRY // KEY INDICATORS",
            metrics=[],
            is_placeholder=True,
        )
    )

    # 3. Isolated Deterministic Chart / Graph Slot (Matplotlib -> CID PNG)
    builder.add_block(
        ChartImageBlock(
            chart_id="weekly_primary_chart",
            title="Weekly Signal & Infrastructure Trajectory",
            chart_type="line",
            labels=[],
            series=[],
            is_placeholder=True,
        )
    )

    # 4. Isolated Deterministic Data Table Slot
    builder.add_block(
        DataTableBlock(
            table_id="weekly_data_ledger",
            title="Weekly Sector & Signal Ledger",
            columns=[],
            rows=[],
            is_placeholder=True,
        )
    )

    # 5. Isolated Written/LLM Narrative Slot (Closing Vector)
    builder.add_block(
        TextSectionBlock(
            section_id="weekly_forward_vector",
            kicker="PART II // FORWARD VECTOR",
            heading="The Week Ahead",
            paragraphs=[],
            is_placeholder=True,
        )
    )

    return builder


def build_welcome_email() -> NewsletterBuilder:
    """Builds the immediate Welcome/Confirmation email sent upon signup."""
    today_label = datetime.datetime.now().strftime("%B %d, %Y")
    builder = NewsletterBuilder(
        subject="Welcome to The New World Grid // Sunday Intelligence Briefing",
        edition_label="SUBSCRIPTION CONFIRMED",
        date_label=today_label,
        preheader="You are locked in for The New World Grid Sunday Briefing.",
    )

    builder.add_block(
        TextSectionBlock(
            section_id="welcome_intro",
            kicker="TRANSMISSION ESTABLISHED",
            heading="Welcome to The New World Grid.",
            paragraphs=[
                "Your email is now registered for our weekly Sunday Briefing—dispatched every Sunday evening at 7:30 PM EST.",
                "Each edition serves as a high-signal recap of the prior week across energy infrastructure, predictive geopolitics, space & industrial acceleration, and sovereign optimism—combining written synthesis with hard tabular data and telemetry.",
            ],
            callout="Zero noise. Zero tracking pixels. Reply directly to this address anytime, or reply 'UNSUBSCRIBE' to opt out instantly.",
        )
    )

    builder.add_block(
        DataTableBlock(
            table_id="welcome_channels",
            title="Live Intelligence Channels on thenewworldgrid.com",
            columns=["Channel", "Focus Area", "Cadence"],
            rows=[
                ["State of the Grid", "Energy, ERCOT load, infrastructure & grid capex", "Daily + Sunday Recap"],
                ["Predictive News", "Global geopolitical signals & probability vectors", "Daily + Sunday Recap"],
                ["Final Frontier", "Space, EV, battery & deep-tech industrial scaling", "Daily + Sunday Recap"],
                ["Daily Optimism", "Constructive human & technological breakthroughs", "Daily + Sunday Recap"],
            ],
        )
    )

    return builder


# ==============================================================================
# 3. SUBSCRIBER DATABASE, GOOGLE SHEET SYNC & SMTP/IMAP ENGINE
# ==============================================================================

class SubscriberManager:
    """Manages local SQLite subscriber ledger, Google Sheet sync, IMAP polling, and SMTP dispatch."""

    def __init__(self, db_path: Path = NWG_SUBSCRIBERS_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    email TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'active',
                    source TEXT NOT NULL DEFAULT 'web_form',
                    subscribed_at TEXT NOT NULL,
                    unsubscribed_at TEXT DEFAULT '',
                    welcome_sent INTEGER NOT NULL DEFAULT 0,
                    last_edition_sent TEXT DEFAULT '',
                    notes TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS editions_log (
                    edition_id TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    recipient_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    details TEXT DEFAULT ''
                )
                """
            )
            conn.commit()

    def upsert_subscriber(
        self,
        raw_email: str,
        source: str = "web_form",
        status: str = "active",
        subscribed_at: Optional[str] = None,
        welcome_sent: Optional[int] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Adds or updates a subscriber in SQLite.
        Returns (is_newly_activated, subscriber_row_dict).
        """
        clean = normalize_email(raw_email)
        if not clean:
            return False, None

        now_iso = subscribed_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_newly_activated = False

        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM subscribers WHERE email = ?", (clean,)).fetchone()
            if existing is None:
                w_flag = int(welcome_sent) if welcome_sent is not None else 0
                conn.execute(
                    """
                    INSERT INTO subscribers (email, status, source, subscribed_at, welcome_sent)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean, status, source, now_iso, w_flag),
                )
                is_newly_activated = status == "active"
            else:
                prev_status = existing["status"]
                new_welcome = int(welcome_sent) if welcome_sent is not None else existing["welcome_sent"]
                if status == "unsubscribed":
                    conn.execute(
                        """
                        UPDATE subscribers
                        SET status = 'unsubscribed', unsubscribed_at = ?
                        WHERE email = ?
                        """,
                        (now_iso, clean),
                    )
                elif status == "active" and prev_status != "active":
                    conn.execute(
                        """
                        UPDATE subscribers
                        SET status = 'active', subscribed_at = ?, unsubscribed_at = '', welcome_sent = ?
                        WHERE email = ?
                        """,
                        (now_iso, new_welcome, clean),
                    )
                    is_newly_activated = True
                elif welcome_sent is not None and int(welcome_sent) > existing["welcome_sent"]:
                    conn.execute(
                        "UPDATE subscribers SET welcome_sent = ? WHERE email = ?",
                        (int(welcome_sent), clean),
                    )
            conn.commit()
            row = conn.execute("SELECT * FROM subscribers WHERE email = ?", (clean,)).fetchone()
            return is_newly_activated, (dict(row) if row else None)

    def mark_unsubscribed(self, raw_email: str) -> bool:
        clean = normalize_email(raw_email)
        if not clean:
            return False
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE subscribers SET status = 'unsubscribed', unsubscribed_at = ? WHERE email = ?",
                (now_iso, clean),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_welcome_sent(self, raw_email: str) -> None:
        clean = normalize_email(raw_email)
        if not clean:
            return
        with self._connect() as conn:
            conn.execute("UPDATE subscribers SET welcome_sent = 1 WHERE email = ?", (clean,))
            conn.commit()

    def get_active_subscribers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM subscribers WHERE status = 'active' ORDER BY subscribed_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_pending_welcome_subscribers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM subscribers WHERE status = 'active' AND welcome_sent = 0 ORDER BY subscribed_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            active_cnt = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE status = 'active'"
            ).fetchone()[0]
            unsub_cnt = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE status = 'unsubscribed'"
            ).fetchone()[0]
            pending_welcome = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE status = 'active' AND welcome_sent = 0"
            ).fetchone()[0]
            last_edition = conn.execute(
                "SELECT * FROM editions_log ORDER BY sent_at DESC LIMIT 1"
            ).fetchone()
            return {
                "active_subscribers": active_cnt,
                "unsubscribed_count": unsub_cnt,
                "pending_welcome": pending_welcome,
                "last_edition": dict(last_edition) if last_edition else None,
                "sender_email": NWG_GMAIL_USER,
                "smtp_configured": bool(NWG_GMAIL_APP_PASSWORD),
                "db_path": str(self.db_path),
            }

    def has_edition_been_sent(self, edition_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM editions_log WHERE edition_id = ? AND status = 'SENT'",
                (edition_id,),
            ).fetchone()
            return row is not None

    def record_edition_sent(
        self, edition_id: str, subject: str, recipient_count: int, status: str = "SENT", details: str = ""
    ) -> None:
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO editions_log (edition_id, sent_at, subject, recipient_count, status, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (edition_id, now_iso, subject, recipient_count, status, details),
            )
            if status == "SENT":
                conn.execute(
                    "UPDATE subscribers SET last_edition_sent = ? WHERE status = 'active'",
                    (edition_id,),
                )
            conn.commit()

    # --------------------------------------------------------------------------
    # SMTP & IMAP Transport
    # --------------------------------------------------------------------------

    def send_email_message(self, msg: EmailMessage) -> bool:
        """Sends an EmailMessage via Gmail SMTP SSL (smtp.gmail.com:465)."""
        if not NWG_GMAIL_APP_PASSWORD:
            print("  [!] NWG_GMAIL_APP_PASSWORD not set in .env; skipping live SMTP send.")
            return False
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=25) as server:
            server.login(NWG_GMAIL_USER, NWG_GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True

    def dispatch_pending_welcomes(self) -> int:
        """Sends immediate Welcome Emails to any active subscribers with welcome_sent == 0."""
        pending = self.get_pending_welcome_subscribers()
        if not pending:
            return 0
        if not NWG_GMAIL_APP_PASSWORD:
            print(f"  [*] {len(pending)} subscriber(s) awaiting welcome email (set NWG_GMAIL_APP_PASSWORD to send).")
            return 0

        builder = build_welcome_email()
        sent_count = 0
        for sub in pending:
            addr = sub["email"]
            try:
                msg = builder.to_email_message(recipient_email=addr)
                if self.send_email_message(msg):
                    self.mark_welcome_sent(addr)
                    sent_count += 1
                    print(f"  [+] Sent Welcome Email to {addr}")
            except Exception as e:
                print(f"  [!] Failed to send Welcome Email to {addr}: {e}")
        return sent_count

    def sync_google_sheet(self) -> Dict[str, int]:
        """
        Bidirectionally syncs the Google Sheet 'Subscribers' tab with local SQLite.
        - Uses the 24/7 Google Apps Script Web App bridge (nwg_sync_subscribers) first
          so zero extra OAuth dependencies are required, with gspread fallback.
        - Pulls new website signups captured 24/7 by Google Apps Script.
        - Updates the sheet with any IMAP signups/unsubscribes and Welcome_Sent flags.
        """
        summary = {"pulled_new": 0, "pushed_to_sheet": 0, "welcomes_sent": 0}
        if APPS_SCRIPT_URL:
            try:
                # 1. Pull remote rows from Google Sheet via Apps Script Web App
                resp = requests.post(
                    APPS_SCRIPT_URL,
                    json={"action": "nwg_sync_subscribers", "subscribers": []},
                    timeout=15,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    remote_subs = payload.get("subscribers", []) if isinstance(payload, dict) else []
                    remote_map = {}
                    for item in remote_subs:
                        em = normalize_email(item.get("email", ""))
                        if not em:
                            continue
                        st = str(item.get("status") or "active").lower()
                        src = str(item.get("source") or "web_form")
                        sub_at = str(item.get("subscribed_at") or "") or None
                        wel_int = 1 if item.get("welcome_sent") else None
                        is_new, _ = self.upsert_subscriber(
                            raw_email=em,
                            source=src,
                            status=st,
                            subscribed_at=sub_at,
                            welcome_sent=wel_int,
                        )
                        if is_new:
                            summary["pulled_new"] += 1
                        remote_map[em] = item

                    # 2. Send immediate Welcome Emails for any newly discovered active subscribers
                    summary["welcomes_sent"] = self.dispatch_pending_welcomes()

                    # 3. Push any local SQLite additions or updated welcome_sent/status flags back to Sheet
                    with self._connect() as conn:
                        local_rows = [dict(r) for r in conn.execute("SELECT * FROM subscribers").fetchall()]

                    to_push = []
                    for lr in local_rows:
                        em = lr["email"]
                        rem = remote_map.get(em)
                        if rem is None or rem.get("status") != lr["status"] or int(rem.get("welcome_sent", 0)) != int(lr["welcome_sent"]):
                            to_push.append(lr)

                    if to_push:
                        requests.post(
                            APPS_SCRIPT_URL,
                            json={"action": "nwg_sync_subscribers", "subscribers": to_push},
                            timeout=15,
                        )
                        summary["pushed_to_sheet"] = len(to_push)
                    return summary
            except Exception as e:
                print(f"  [!] Apps Script subscriber sync fallback notice: {e}")

        if not SERVICE_ACCOUNT_FILE.exists():
            return summary

        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials

            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(str(SERVICE_ACCOUNT_FILE), scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

            headers = ["Email", "Status", "Source", "Subscribed_At", "Welcome_Sent", "Updated_At"]
            try:
                ws = spreadsheet.worksheet(NWG_SUBSCRIBERS_TAB)
            except gspread.exceptions.WorksheetNotFound:
                ws = spreadsheet.add_worksheet(title=NWG_SUBSCRIBERS_TAB, rows=500, cols=6)
                ws.append_row(headers)

            all_values = ws.get_all_values()
            if not all_values:
                ws.append_row(headers)
                all_values = [headers]

            sheet_map: Dict[str, Tuple[int, List[str]]] = {}
            for r_idx, row in enumerate(all_values[1:], start=2):
                if not row or not row[0].strip():
                    continue
                em = normalize_email(row[0])
                if not em:
                    continue
                st = (row[1].strip().lower() if len(row) > 1 and row[1].strip() else "active")
                src = (row[2].strip() if len(row) > 2 and row[2].strip() else "web_form")
                sub_at = (row[3].strip() if len(row) > 3 and row[3].strip() else None)
                wel_raw = (row[4].strip().upper() if len(row) > 4 else "")
                wel_int = 1 if wel_raw in ("1", "YES", "TRUE", "SENT") else None

                is_new, _ = self.upsert_subscriber(
                    raw_email=em,
                    source=src,
                    status=st,
                    subscribed_at=sub_at,
                    welcome_sent=wel_int,
                )
                if is_new:
                    summary["pulled_new"] += 1
                sheet_map[em] = (r_idx, row)

            # Dispatch immediate welcome emails for any newly discovered active signups
            summary["welcomes_sent"] = self.dispatch_pending_welcomes()

            # Push local SQLite state back to Sheet where missing or out of sync
            with self._connect() as conn:
                local_rows = conn.execute("SELECT * FROM subscribers ORDER BY subscribed_at ASC").fetchall()

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for lr in local_rows:
                em = lr["email"]
                wel_str = "YES" if lr["welcome_sent"] else "PENDING"
                if em not in sheet_map:
                    ws.append_row([em, lr["status"], lr["source"], lr["subscribed_at"], wel_str, now_str])
                    summary["pushed_to_sheet"] += 1
                else:
                    r_idx, s_row = sheet_map[em]
                    cur_status = s_row[1].strip().lower() if len(s_row) > 1 else ""
                    cur_wel = s_row[4].strip().upper() if len(s_row) > 4 else ""
                    if cur_status != lr["status"] or (wel_str == "YES" and cur_wel != "YES"):
                        ws.update(
                            f"B{r_idx}:F{r_idx}",
                            [[lr["status"], lr["source"], lr["subscribed_at"], wel_str, now_str]],
                        )
        except Exception as e:
            print(f"  [!] Google Sheet subscriber sync warning: {e}")

        return summary

    def sync_imap_inbox(self) -> Dict[str, int]:
        """
        Polls thenewworldgrid@gmail.com via IMAP SSL (imap.gmail.com:993) for:
        1. 'unsubscribe' replies -> marks subscriber unsubscribed.
        2. Emailed signups (e.g. forwarded from anything@thenewworldgrid.com) -> subscribes & welcomes.
        """
        result = {"new_subscribers": 0, "unsubscribes": 0}
        if not NWG_GMAIL_APP_PASSWORD:
            return result

        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(NWG_GMAIL_USER, NWG_GMAIL_APP_PASSWORD)
            mail.select("INBOX")

            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                mail.logout()
                return result

            msg_ids = data[0].split()
            for m_id in msg_ids:
                res, msg_data = mail.fetch(m_id, "(RFC822)")
                if res != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_bytes = msg_data[0][1]
                parsed = email.message_from_bytes(raw_bytes, policy=email.policy.default)

                sender_addr = normalize_email(parsed.get("Reply-To") or parsed.get("From") or "")
                if not sender_addr or sender_addr == normalize_email(NWG_GMAIL_USER):
                    continue
                if "noreply" in sender_addr or "no-reply" in sender_addr or "mailer-daemon" in sender_addr:
                    continue

                subject_str = str(parsed.get("Subject") or "").strip()
                to_str = str(parsed.get("To") or "").lower()
                body_preview = ""
                try:
                    body_part = parsed.get_body(preferencelist=("plain", "html"))
                    if body_part:
                        body_preview = body_part.get_content()[:500]
                except Exception:
                    pass

                combined_low = f"{subject_str}\n{body_preview}".lower()
                if any(k in combined_low for k in ("unsubscribe", "opt out", "opt-out", "remove me")):
                    if self.mark_unsubscribed(sender_addr):
                        result["unsubscribes"] += 1
                        print(f"  [-] IMAP Unsubscribe processed: {sender_addr}")
                elif (
                    "thenewworldgrid.com" in to_str
                    or any(k in combined_low for k in ("subscribe", "sign up", "signup", "newsletter", "briefing"))
                ):
                    is_new, _ = self.upsert_subscriber(sender_addr, source="imap_email", status="active")
                    if is_new:
                        result["new_subscribers"] += 1
                        print(f"  [+] IMAP New Subscriber added: {sender_addr}")

            mail.logout()
        except Exception as e:
            print(f"  [!] IMAP sync warning: {e}")

        if result["new_subscribers"] > 0:
            self.dispatch_pending_welcomes()

        return result


# ==============================================================================
# 4. CLI & AUTOMATED DISPATCH ENTRY POINTS
# ==============================================================================

def send_telegram_alert(html_text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": html_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception:
        pass


def has_scaffold_placeholders(builder: NewsletterBuilder) -> bool:
    """Returns True if any block in the builder is still marked as an empty placeholder."""
    return any(getattr(b, "is_placeholder", False) for b in builder.blocks)


def export_preview(builder: NewsletterBuilder, output_path: Optional[Path] = None) -> Path:
    """Writes a standalone HTML preview (converting CID images to base64 data URIs for browser viewing)."""
    import base64

    target = output_path or (DATA_DIR / "preview_weekly_recap.html")
    html_body, _, attachments = builder.render(unsubscribe_email="preview@thenewworldgrid.com")
    for att in attachments:
        b64 = base64.b64encode(att.png_bytes).decode("ascii")
        html_body = html_body.replace(f"cid:{att.chart_id}", f"data:image/png;base64,{b64}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_body, encoding="utf-8")
    return target


def run_weekly_dispatch(
    manager: SubscriberManager,
    builder: Optional[NewsletterBuilder] = None,
    force: bool = False,
    allow_scaffold: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executes the Sunday 7:30 PM EST Weekly Recap dispatch.
    Includes safeguards so empty placeholder scaffolds are not emailed to live subscribers
    unless --allow-scaffold is explicitly passed.
    """
    edition_id, range_label, _ = get_prior_week_window()
    active_builder = builder or build_weekly_recap_scaffold()

    if not force and manager.has_edition_been_sent(edition_id):
        return {
            "ok": True,
            "status": "ALREADY_SENT",
            "edition_id": edition_id,
            "message": f"Edition {edition_id} has already been dispatched this week.",
        }

    # Always write preview file to disk
    preview_file = export_preview(active_builder)

    if has_scaffold_placeholders(active_builder) and not allow_scaffold:
        msg = (
            f"Edition {edition_id} ({range_label}) scaffold rendered to {preview_file.name}. "
            "Live SMTP dispatch paused because content slots are currently in empty scaffold mode."
        )
        print(f"  [*] {msg}")
        return {
            "ok": True,
            "status": "SCAFFOLD_PAUSED",
            "edition_id": edition_id,
            "preview_path": str(preview_file),
            "message": msg,
        }

    # Sync subscribers first
    manager.sync_imap_inbox()
    manager.sync_google_sheet()
    subscribers = manager.get_active_subscribers()

    if dry_run:
        return {
            "ok": True,
            "status": "DRY_RUN",
            "edition_id": edition_id,
            "recipient_count": len(subscribers),
            "preview_path": str(preview_file),
        }

    if not NWG_GMAIL_APP_PASSWORD:
        return {
            "ok": False,
            "status": "MISSING_APP_PASSWORD",
            "edition_id": edition_id,
            "message": "NWG_GMAIL_APP_PASSWORD is not configured in .env.",
        }

    sent_count = 0
    for sub in subscribers:
        addr = sub["email"]
        try:
            mime_msg = active_builder.to_email_message(recipient_email=addr)
            if manager.send_email_message(mime_msg):
                sent_count += 1
        except Exception as e:
            print(f"  [!] Failed to send weekly edition {edition_id} to {addr}: {e}")

    manager.record_edition_sent(
        edition_id=edition_id,
        subject=active_builder.subject,
        recipient_count=sent_count,
        status="SENT",
        details=f"Dispatched to {sent_count}/{len(subscribers)} active subscribers",
    )

    if obsidian_bridge:
        obsidian_bridge.log_execution(
            "newsletter_engine",
            "🟢 Success",
            f"Dispatched Weekly Recap {edition_id} to {sent_count} subscriber(s)",
            host="Home-Laptop",
        )

    send_telegram_alert(
        f"📬 <b>NEW WORLD GRID — SUNDAY BRIEFING SENT</b>\n"
        f"• <b>Edition:</b> <code>{edition_id}</code> ({range_label})\n"
        f"• <b>Sender:</b> <code>{NWG_GMAIL_USER}</code>\n"
        f"• <b>Recipients:</b> {sent_count}/{len(subscribers)}"
    )

    return {
        "ok": True,
        "status": "SENT",
        "edition_id": edition_id,
        "recipient_count": sent_count,
        "preview_path": str(preview_file),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="New World Grid Open-Source Newsletter Engine ([aeOS:Home:Newsletter])")
    parser.add_argument("--sync", action="store_true", help="Sync subscribers with Google Sheet + IMAP and send pending Welcome Emails")
    parser.add_argument("--send-weekly", action="store_true", help="Build and dispatch the Sunday Weekly Recap edition")
    parser.add_argument("--preview", action="store_true", help="Render the Weekly Recap scaffold HTML preview to disk")
    parser.add_argument("--status", action="store_true", help="Print subscriber and newsletter engine status JSON")
    parser.add_argument("--add", type=str, help="Manually add a subscriber email address")
    parser.add_argument("--unsubscribe", type=str, help="Mark an email address as unsubscribed")
    parser.add_argument("--force", action="store_true", help="Bypass weekly duplicate send lock")
    parser.add_argument("--allow-scaffold", action="store_true", help="Allow sending even if placeholder slots are present")
    parser.add_argument("--dry-run", action="store_true", help="Simulate weekly send without SMTP transmission")
    args = parser.parse_args()

    manager = SubscriberManager()

    if args.add:
        is_new, row = manager.upsert_subscriber(args.add, source="manual_cli", status="active")
        if not row:
            print(f"[!] Invalid email address: {args.add}")
            sys.exit(1)
        manager.dispatch_pending_welcomes()
        manager.sync_google_sheet()
        print(json.dumps({"ok": True, "is_new": is_new, "subscriber": row}, indent=2))
        return

    if args.unsubscribe:
        changed = manager.mark_unsubscribed(args.unsubscribe)
        manager.sync_google_sheet()
        print(json.dumps({"ok": True, "unsubscribed": changed, "email": args.unsubscribe}, indent=2))
        return

    if args.sync:
        imap_res = manager.sync_imap_inbox()
        sheet_res = manager.sync_google_sheet()
        stats = manager.get_stats()
        print(json.dumps({"ok": True, "imap": imap_res, "sheet": sheet_res, "stats": stats}, indent=2))
        return

    if args.preview:
        scaffold = build_weekly_recap_scaffold()
        out = export_preview(scaffold)
        print(json.dumps({"ok": True, "preview_path": str(out)}, indent=2))
        return

    if args.send_weekly:
        res = run_weekly_dispatch(
            manager=manager,
            force=args.force,
            allow_scaffold=args.allow_scaffold,
            dry_run=args.dry_run,
        )
        print(json.dumps(res, indent=2))
        return

    # Default or --status
    stats = manager.get_stats()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
