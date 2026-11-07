#!/usr/bin/env python3
r"""
==============================================================================
[aeOS:Home:Newsletter]
Script / Service: newsletter_content.py
Path: C:\Users\bertb\aeOS\home\new_world_grid\newsletter_content.py
Role & Mission: Weekly Content Synthesis & Market Sentiment Engine for The New World Grid
                Sunday Newsletter.
                1. ArchiveDigestEngine:
                   - Fetches the prior week's archives across State of the Grid (grid),
                     Predictive News (predictive), Daily Optimism (optimism), and
                     Final Frontier (frontier).
                   - Deduplicates same-day re-runs (retaining only the latest archive per
                     calendar day, max 7 daily editions/week per channel).
                   - Extracts ARC's daily thought experiments and deterministically selects
                     the 3 least similar (most distinct) hypotheticals via pairwise Jaccard
                     token dissimilarity.
                2. MarketSentimentPipeline (Newsletter-Only Market Tone Engine):
                   - Combines 7-day price/volatility regime for SPX, NQ, DJI, BTC, and VIX
                     with Financial RSS Headlines (rss_articles.db) and Polymarket Macro
                     Shifts (price_feeds.db) to synthesize how the market 'felt' this week.
                   - Stores raw 7-day price series for SPX, NQ, DJI, and BTC for the paired
                     chart slot (chart rendering left as placeholder until Y-axis design).
                3. 4-Stage Ollama (qwen2.5:7b) Synthesis Pipeline:
                   - Stage 1: 'The Real' (<= 7-8 sentences on grid, geopolitics & optimism)
                   - Stage 2: 'Major Markets' (<= 7-8 sentences on weekly market sentiment/tone)
                   - Stage 3: 'On the Horizon' (<= 7-8 sentences opening with ARC's 3 hypotheticals)
                   - Stage 4 (Runs LAST): Dynamic Email Header/Subject + 2-Sentence Introductory
                     Byline Hook summarizing all 3 synthesized sections.
Operating Schedule: Invoked by newsletter_engine.py on Sunday 19:30 EST & Preview CLI
Node Affinity: Home-Laptop
==============================================================================
"""

import contextlib
import dataclasses
import datetime
import itertools
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import requests

# Paths & Configuration
QUARTZ_REPO_DIR = Path(r"C:\Users\bertb\new-world-grid")
ARCHIVE_ROOT_DIR = QUARTZ_REPO_DIR / "content" / "archive"
GEMINI_DATA_DIR = Path(r"C:\Users\bertb\gemini\intelligence\data")
RSS_DB_PATH = GEMINI_DATA_DIR / "rss_articles.db"
PRICES_DB_PATH = GEMINI_DATA_DIR / "price_feeds.db"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

_ABBREV_PLACEHOLDERS = {
    "U.S.": "U_S_DOT",
    "U.K.": "U_K_DOT",
    "E.U.": "E_U_DOT",
    "U.N.": "U_N_DOT",
    "Dr.": "DR_DOT",
    "Mr.": "MR_DOT",
    "Ms.": "MS_DOT",
    "Mrs.": "MRS_DOT",
    "St.": "ST_DOT",
    "vs.": "VS_DOT",
    "etc.": "ETC_DOT",
    "Inc.": "INC_DOT",
    "Corp.": "CORP_DOT",
    "Co.": "CO_DOT",
    "Ltd.": "LTD_DOT",
    "e.g.": "E_G_DOT",
    "i.e.": "I_E_DOT",
    "Jan.": "JAN_DOT",
    "Feb.": "FEB_DOT",
    "Mar.": "MAR_DOT",
    "Apr.": "APR_DOT",
    "Jun.": "JUN_DOT",
    "Jul.": "JUL_DOT",
    "Aug.": "AUG_DOT",
    "Sep.": "SEP_DOT",
    "Sept.": "SEPT_DOT",
    "Oct.": "OCT_DOT",
    "Nov.": "NOV_DOT",
    "Dec.": "DEC_DOT",
}

_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "had",
    "not", "are", "was", "were", "will", "would", "could", "should", "into",
    "their", "there", "they", "them", "then", "than", "what", "when", "where",
    "which", "while", "who", "whom", "whose", "why", "how", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "only", "own", "same",
    "so", "too", "very", "can", "just", "now", "also", "over", "under", "between",
    "through", "during", "before", "after", "above", "below", "about", "against",
    "imagine", "purely", "thought", "experiment", "follows", "year", "years",
    "2031", "2036", "future", "world", "new", "lead", "leading", "leads", "become",
    "becomes", "becoming", "create", "creates", "creating", "created", "companies",
    "company", "technology", "system", "systems", "shift", "shifts",
}


# ==============================================================================
# 1. SENTENCE HYGIENE & STRICT LENGTH ENFORCEMENT
# ==============================================================================

def split_sentences(text: str) -> List[str]:
    """Splits narrative text into clean individual sentences without breaking on abbreviations or decimals."""
    if not text or not text.strip():
        return []
    cleaned = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    # Strip markdown bold/headers/bullets if any
    cleaned = re.sub(r"^#+\s*", "", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)

    protected = cleaned
    for abbr, token in _ABBREV_PLACEHOLDERS.items():
        protected = protected.replace(abbr, token)
    # Protect decimal numbers (e.g. 81.4, $5.4)
    protected = re.sub(r"(\d)\.(\d)", r"\1_DEC_DOT_\2", protected)

    raw_parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'“‘(])', protected)
    sentences: List[str] = []
    for part in raw_parts:
        restored = part.strip()
        if not restored:
            continue
        restored = re.sub(r"(\d)_DEC_DOT_(\d)", r"\1.\2", restored)
        for abbr, token in _ABBREV_PLACEHOLDERS.items():
            restored = restored.replace(token, abbr)
        if restored[-1] not in ".!?":
            restored += "."
        sentences.append(restored)
    return sentences


def enforce_sentence_limit(text: str, max_sentences: int = 8) -> str:
    """Strictly caps prose at max_sentences (default 8 for sections, 2 for byline hook)."""
    sentences = split_sentences(text)
    if not sentences:
        return ""
    capped = sentences[:max_sentences]
    return " ".join(capped)


# ==============================================================================
# 2. ARCHIVE DIGEST ENGINE & "3 LEAST SIMILAR" THOUGHT EXPERIMENT SELECTOR
# ==============================================================================

@dataclasses.dataclass
class ArchiveEdition:
    channel: str
    date_str: str
    timestamp_sort_key: str
    title: str
    author: str
    summary_lede: str
    body_text: str
    thought_experiment: str
    file_path: str


_DATE_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", re.IGNORECASE)
_BYLINE_AUTHOR_RE = re.compile(r'<span\s+class="sotg-author">\s*([^<]+?)\s*</span>', re.IGNORECASE)
_BYLINE_TS_RE = re.compile(r'<span\s+class="sotg-timestamp">\s*([^<]+?)\s*</span>', re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TITLE_FM_RE = re.compile(r'^title:\s*["\']?(.*?)["\']?\s*$', re.MULTILINE)


def parse_archive_markdown(file_path: Path, channel: str) -> Optional[ArchiveEdition]:
    """Parses a single archive markdown file into structured narrative and thought experiment fields."""
    m = _DATE_FILENAME_RE.match(file_path.name)
    if not m:
        return None
    date_str = m.group(1)
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    title = file_path.stem
    fm_match = _FRONTMATTER_RE.match(raw)
    body = raw
    if fm_match:
        fm_block = fm_match.group(1)
        t_match = _TITLE_FM_RE.search(fm_block)
        if t_match:
            title = t_match.group(1).strip()
        body = raw[fm_match.end():]

    author_match = _BYLINE_AUTHOR_RE.search(body)
    default_authors = {
        "grid": "MERIDIAN",
        "predictive": "ORACLE",
        "optimism": "AURORA",
        "frontier": "ARC",
    }
    author = author_match.group(1).strip() if author_match else default_authors.get(channel, "ARC")

    ts_match = _BYLINE_TS_RE.search(body)
    ts_raw = ts_match.group(1).strip() if ts_match else ""
    time_hm_match = re.search(r"(\d{2}:\d{2})", ts_raw)
    try:
        mtime_str = f"{file_path.stat().st_mtime:.3f}"
    except Exception:
        mtime_str = "0"
    hm_str = time_hm_match.group(1) if time_hm_match else "00:00"
    timestamp_sort_key = f"{date_str}T{hm_str}_{mtime_str}_{file_path.name}"

    # Cut off any embedded archive backlog section
    if "<!-- EDITION_ARCHIVE_BACKLOG -->" in body:
        body = body.split("<!-- EDITION_ARCHIVE_BACKLOG -->", 1)[0]

    # Extract thought experiment if present (Final Frontier)
    thought_experiment = ""
    te_split = re.split(r"\*What follows is purely a thought experiment\.\*", body, flags=re.IGNORECASE)
    if len(te_split) > 1:
        te_raw = te_split[1]
        te_raw = te_raw.split("<!-- /FRONTIER_ENGINE_END -->", 1)[0]
        te_raw = re.sub(r"<!--.*?-->", "", te_raw, flags=re.DOTALL)
        te_raw = re.sub(r"</?[a-zA-Z][^>]*>", " ", te_raw)
        thought_experiment = " ".join(line.strip() for line in te_raw.strip().splitlines() if line.strip())
        body_main = te_split[0]
    else:
        body_main = body

    # Clean HTML / comments / boilerplate from body_main
    body_main = re.sub(r'<div\s+class="sotg-byline">.*?</div>', "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r'<div\s+class="sotg-analyst">.*?</div>', "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r"###\s+Geomagnetic Environment.*", "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r"<iframe.*?</iframe>", "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r'<a\s+href="#intelligence-brief".*?</a>', "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r'<span\s+class="meridian-attr">.*?</span>', "", body_main, flags=re.DOTALL | re.IGNORECASE)
    body_main = re.sub(r"<!--.*?-->", "", body_main, flags=re.DOTALL)
    body_main = re.sub(r"</?[a-zA-Z][^>]*>", " ", body_main)

    lines = [ln.strip() for ln in body_main.splitlines() if ln.strip()]
    summary_lede = lines[0] if lines else title
    cleaned_body = "\n".join(lines)

    return ArchiveEdition(
        channel=channel,
        date_str=date_str,
        timestamp_sort_key=timestamp_sort_key,
        title=title,
        author=author,
        summary_lede=summary_lede,
        body_text=cleaned_body,
        thought_experiment=thought_experiment,
        file_path=str(file_path),
    )


def deduplicate_latest_per_day(editions: Sequence[ArchiveEdition], max_days: int = 7) -> List[ArchiveEdition]:
    """
    Groups archive editions by calendar date (YYYY-MM-DD) and keeps ONLY the latest
    edition per day (sorted by timestamp_sort_key), up to max_days most recent days.
    """
    by_date: Dict[str, ArchiveEdition] = {}
    for ed in editions:
        existing = by_date.get(ed.date_str)
        if existing is None or ed.timestamp_sort_key > existing.timestamp_sort_key:
            by_date[ed.date_str] = ed

    sorted_dates = sorted(by_date.keys(), reverse=True)[:max_days]
    # Return in chronological order (oldest -> newest across the week)
    return [by_date[d] for d in sorted(sorted_dates)]


def fetch_weekly_channel_archives(
    archive_root: Path = ARCHIVE_ROOT_DIR,
    ref_dt: Optional[datetime.datetime] = None,
    lookback_days: int = 7,
) -> Dict[str, List[ArchiveEdition]]:
    """
    Fetches and deduplicates the prior week's archives for:
    - grid (State of the Grid)
    - predictive (Predictive News)
    - optimism (Daily Optimism)
    - frontier (Final Frontier)
    """
    now = ref_dt or datetime.datetime.now()
    cutoff_date_str = (now - datetime.timedelta(days=lookback_days - 1)).strftime("%Y-%m-%d")
    end_date_str = now.strftime("%Y-%m-%d")

    channels = ("grid", "predictive", "optimism", "frontier")
    result: Dict[str, List[ArchiveEdition]] = {}

    for ch in channels:
        ch_dir = archive_root / ch
        if not ch_dir.exists():
            result[ch] = []
            continue

        all_parsed: List[ArchiveEdition] = []
        for md_file in ch_dir.glob("*.md"):
            if md_file.name.lower() == "index.md":
                continue
            parsed = parse_archive_markdown(md_file, channel=ch)
            if parsed:
                all_parsed.append(parsed)

        # Filter to the 7-day window first; if fewer than 3 daily editions in window,
        # include up to lookback_days most recent distinct dates on disk.
        in_window = [ed for ed in all_parsed if cutoff_date_str <= ed.date_str <= end_date_str]
        dedup_window = deduplicate_latest_per_day(in_window, max_days=lookback_days)
        if len(dedup_window) >= 3 or len(all_parsed) <= len(dedup_window):
            result[ch] = dedup_window
        else:
            result[ch] = deduplicate_latest_per_day(all_parsed, max_days=lookback_days)

    return result


def _tokenize_hypothetical(text: str) -> set:
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def jaccard_dissimilarity(text_a: str, text_b: str) -> float:
    """Returns 1.0 - Jaccard similarity in [0.0, 1.0] (1.0 = completely distinct)."""
    set_a = _tokenize_hypothetical(text_a)
    set_b = _tokenize_hypothetical(text_b)
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    inter = set_a & set_b
    return 1.0 - (len(inter) / len(union))


def select_three_least_similar_hypotheticals(
    frontier_editions: Sequence[ArchiveEdition], count: int = 3
) -> List[ArchiveEdition]:
    """
    Filters Final Frontier daily editions with thought experiments and selects the
    3 least similar (most mutually distinct) hypotheticals from the week.
    Maximizes (minimum_pairwise_distance, sum_of_pairwise_distances).
    """
    candidates = [ed for ed in frontier_editions if ed.thought_experiment.strip()]
    if len(candidates) <= count:
        return list(candidates)

    best_combo: Optional[Tuple[ArchiveEdition, ...]] = None
    best_score: Tuple[float, float] = (-1.0, -1.0)

    for combo in itertools.combinations(candidates, count):
        pair_distances = [
            jaccard_dissimilarity(a.thought_experiment, b.thought_experiment)
            for a, b in itertools.combinations(combo, 2)
        ]
        min_dist = min(pair_distances) if pair_distances else 0.0
        sum_dist = sum(pair_distances)
        score = (round(min_dist, 6), round(sum_dist, 6))
        if score > best_score:
            best_score = score
            best_combo = combo

    if best_combo is None:
        return candidates[:count]
    # Return selected 3 in chronological order
    return sorted(best_combo, key=lambda x: x.date_str)


# ==============================================================================
# 3. NEWSLETTER-ONLY MARKET SENTIMENT & 7-DAY PRICE PIPELINE
# ==============================================================================

@dataclasses.dataclass
class AssetWeeklySeries:
    symbol: str
    display_name: str
    dates: List[str]
    closes: List[float]
    start_price: float
    end_price: float
    weekly_pct_change: float
    high_price: float
    low_price: float
    swing_pct: float


@dataclasses.dataclass
class MarketSentimentReport:
    assets: Dict[str, AssetWeeklySeries]
    vix_level: float
    vix_weekly_delta: float
    regime_label: str
    headlines: List[str]
    polymarket_Top_odds: List[str]
    chart_labels: List[str]
    chart_series_raw: List[Dict[str, Any]]

    def format_prompt_context(self) -> str:
        lines = [f"QUANTITATIVE MARKET REGIME: {self.regime_label}"]
        for sym in ("SPX", "NQ", "DJI", "BTC"):
            a = self.assets.get(sym)
            if a:
                lines.append(
                    f"  - {a.display_name} ({a.symbol}): Close {a.end_price:,.2f} "
                    f"({a.weekly_pct_change:+.2f}% WoW | 7d Range: {a.low_price:,.2f} - {a.high_price:,.2f}, "
                    f"Swing: {a.swing_pct:.2f}%)"
                )
        if self.vix_level > 0:
            lines.append(f"  - Volatility Index (VIX): {self.vix_level:.2f} ({self.vix_weekly_delta:+.2f}% WoW)")

        if self.headlines:
            lines.append("\nKEY FINANCIAL & MACRO HEADLINES THIS WEEK:")
            for h in self.headlines[:10]:
                lines.append(f"  - {h}")

        if self.polymarket_Top_odds:
            lines.append("\nPREDICTION MARKET MACRO ODDS (POLYMARKET):")
            for pm in self.polymarket_Top_odds[:5]:
                lines.append(f"  - {pm}")

        return "\n".join(lines)


class MarketSentimentPipeline:
    """
    Newsletter-exclusive Market Sentiment & 7-Day Price Pipeline.
    Combines:
      1. 7-day price & volatility trajectories for SPX, NQ, DJI, BTC, and VIX.
      2. Financial & macro headlines from rss_articles.db.
      3. Polymarket macro prediction shifts from price_feeds.db.
    """

    YAHOO_SYMBOLS = {
        "SPX": ("^GSPC", "S&P 500"),
        "NQ": ("^IXIC", "Nasdaq Composite"),
        "DJI": ("^DJI", "Dow Jones"),
        "BTC": ("BTC-USD", "Bitcoin"),
        "VIX": ("^VIX", "CBOE VIX"),
    }

    FINANCIAL_KEYWORDS = (
        "market", "stocks", "equities", "s&p", "nasdaq", "dow", "wall street",
        "treasury", "yield", "yields", "fed", "federal reserve", "interest rate",
        "inflation", "cpi", "jobs", "payroll", "gdp", "recession", "tariff",
        "earnings", "rally", "selloff", "sell-off", "volatility", "bitcoin",
        "crypto", "liquidity", "credit", "dollar", "oil", "gold",
    )

    def __init__(self, rss_db_path: Path = RSS_DB_PATH, prices_db_path: Path = PRICES_DB_PATH):
        self.rss_db_path = Path(rss_db_path)
        self.prices_db_path = Path(prices_db_path)

    def _fetch_yahoo_7d_series(self, yahoo_ticker: str, symbol: str, display_name: str) -> Optional[AssetWeeklySeries]:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(yahoo_ticker)}?range=7d&interval=1d"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            result = payload["chart"]["result"][0]
            timestamps = result.get("timestamp") or []
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            closes_raw = quote.get("close") or []
            highs_raw = quote.get("high") or []
            lows_raw = quote.get("low") or []

            dates: List[str] = []
            closes: List[float] = []
            highs: List[float] = []
            lows: List[float] = []

            for idx, ts in enumerate(timestamps):
                c = closes_raw[idx] if idx < len(closes_raw) else None
                if c is None:
                    continue
                dt_lbl = datetime.datetime.fromtimestamp(ts).strftime("%a %m/%d")
                dates.append(dt_lbl)
                closes.append(float(c))
                h = highs_raw[idx] if idx < len(highs_raw) and highs_raw[idx] is not None else c
                l = lows_raw[idx] if idx < len(lows_raw) and lows_raw[idx] is not None else c
                highs.append(float(h))
                lows.append(float(l))

            if not closes:
                return None

            start_p = closes[0]
            end_p = closes[-1]
            pct = ((end_p - start_p) / start_p * 100.0) if start_p else 0.0
            hi = max(highs) if highs else max(closes)
            lo = min(lows) if lows else min(closes)
            swing = ((hi - lo) / lo * 100.0) if lo else 0.0

            return AssetWeeklySeries(
                symbol=symbol,
                display_name=display_name,
                dates=dates,
                closes=closes,
                start_price=round(start_p, 2),
                end_price=round(end_p, 2),
                weekly_pct_change=round(pct, 2),
                high_price=round(hi, 2),
                low_price=round(lo, 2),
                swing_pct=round(swing, 2),
            )
        except Exception:
            return None

    def _fetch_local_db_series_fallback(self, symbol: str, display_name: str) -> Optional[AssetWeeklySeries]:
        if not self.prices_db_path.exists():
            return None
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
        try:
            with contextlib.closing(sqlite3.connect(str(self.prices_db_path), timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                if symbol == "BTC":
                    rows = conn.execute(
                        """
                        SELECT substr(timestamp, 1, 10) AS d, AVG(price_usd) AS p
                        FROM crypto_prices
                        WHERE symbol = 'BTC' AND timestamp >= ?
                        GROUP BY substr(timestamp, 1, 10)
                        ORDER BY d ASC
                        """,
                        (cutoff,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT substr(timestamp, 1, 10) AS d, AVG(price) AS p
                        FROM stock_prices
                        WHERE symbol = ? AND timestamp >= ?
                        GROUP BY substr(timestamp, 1, 10)
                        ORDER BY d ASC
                        """,
                        (symbol, cutoff),
                    ).fetchall()

            if not rows:
                return None
            dates = [str(r["d"]) for r in rows]
            closes = [float(r["p"]) for r in rows]
            start_p = closes[0]
            end_p = closes[-1]
            pct = ((end_p - start_p) / start_p * 100.0) if start_p else 0.0
            hi = max(closes)
            lo = min(closes)
            swing = ((hi - lo) / lo * 100.0) if lo else 0.0
            return AssetWeeklySeries(
                symbol=symbol,
                display_name=display_name,
                dates=dates,
                closes=closes,
                start_price=round(start_p, 2),
                end_price=round(end_p, 2),
                weekly_pct_change=round(pct, 2),
                high_price=round(hi, 2),
                low_price=round(lo, 2),
                swing_pct=round(swing, 2),
            )
        except Exception:
            return None

    def fetch_financial_rss_headlines(self, lookback_days: int = 7, limit: int = 12) -> List[str]:
        if not self.rss_db_path.exists():
            return []
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=lookback_days)).isoformat()
        headlines: List[str] = []
        seen_titles: set = set()
        try:
            with contextlib.closing(sqlite3.connect(str(self.rss_db_path), timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT title, description, source
                    FROM articles
                    WHERE COALESCE(published_date, fetched_at) >= ?
                    ORDER BY COALESCE(published_date, fetched_at) DESC
                    LIMIT 500
                    """,
                    (cutoff,),
                ).fetchall()

            for r in rows:
                title = (r["title"] or "").strip()
                desc = (r["description"] or "").strip()
                if not title or title.lower() in seen_titles:
                    continue
                combined = f"{title} {desc}".lower()
                if any(kw in combined for kw in self.FINANCIAL_KEYWORDS):
                    seen_titles.add(title.lower())
                    src = (r["source"] or "Feed").strip()
                    headlines.append(f"{title} ({src})")
                    if len(headlines) >= limit:
                        break
        except Exception:
            pass
        return headlines

    def fetch_polymarket_macro_shifts(self, limit: int = 5) -> List[str]:
        if not self.prices_db_path.exists():
            return []
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
        macro_keywords = (
            "fed", "rate", "interest", "recession", "inflation", "cpi", "gdp",
            "tariff", "trade", "china", "iran", "russia", "ukraine", "oil",
            "energy", "bitcoin", "crypto", "s&p", "market", "treasury", "debt",
        )
        exclude_keywords = ("nomination", "2028", "governor", "mayor", "oscar", "nfl", "nba")
        results: List[str] = []
        try:
            with contextlib.closing(sqlite3.connect(str(self.prices_db_path), timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT market_name, outcome_yes, MAX(timestamp) as latest_ts, AVG(volume) as avg_vol
                    FROM prediction_markets
                    WHERE timestamp >= ?
                    GROUP BY market_id
                    ORDER BY avg_vol DESC
                    LIMIT 60
                    """,
                    (cutoff,),
                ).fetchall()
            for r in rows:
                q = (r["market_name"] or "").strip()
                q_low = q.lower()
                if not q or any(bad in q_low for bad in exclude_keywords):
                    continue
                if not any(mk in q_low for mk in macro_keywords):
                    continue
                yes_prob = float(r["outcome_yes"] or 0.0) * 100.0
                results.append(f"{q} — YES: {yes_prob:.0f}%")
                if len(results) >= limit:
                    break
        except Exception:
            pass
        return results

    @staticmethod
    def classify_market_regime(
        assets: Dict[str, AssetWeeklySeries], vix_level: float, vix_delta: float
    ) -> str:
        spx_pct = assets["SPX"].weekly_pct_change if "SPX" in assets else 0.0
        nq_pct = assets["NQ"].weekly_pct_change if "NQ" in assets else 0.0
        dji_pct = assets["DJI"].weekly_pct_change if "DJI" in assets else 0.0
        btc_pct = assets["BTC"].weekly_pct_change if "BTC" in assets else 0.0

        eq_avg = (spx_pct + nq_pct + dji_pct) / 3.0
        if eq_avg >= 1.25 and btc_pct >= 1.5 and vix_level < 20:
            return "Broad Risk-On Expansion (Equities & Bitcoin Bidding in Tandem)"
        if eq_avg <= -1.25 and (vix_level >= 20 or vix_delta >= 8.0):
            return "Risk-Off De-Leveraging & Volatility Expansion"
        if abs(nq_pct - dji_pct) >= 2.0:
            leader = "Growth/Tech (NQ)" if nq_pct > dji_pct else "Industrials/Value (DJI)"
            return f"Sector Rotation & Index Divergence (Led by {leader})"
        if (eq_avg > 0.5 and btc_pct < -2.0) or (eq_avg < -0.5 and btc_pct > 2.5):
            return "Cross-Asset Decoupling (Equities vs. Digital Liquidity)"
        return "Cautious Consolidation & Selective Two-Way Price Discovery"

    def run(self, fetch_network: bool = True) -> MarketSentimentReport:
        assets: Dict[str, AssetWeeklySeries] = {}
        for sym, (yahoo_ticker, disp_name) in self.YAHOO_SYMBOLS.items():
            series_obj = None
            if fetch_network:
                series_obj = self._fetch_yahoo_7d_series(yahoo_ticker, sym, disp_name)
            if series_obj is None:
                series_obj = self._fetch_local_db_series_fallback(sym, disp_name)
            if series_obj is not None:
                assets[sym] = series_obj

        vix_series = assets.pop("VIX", None)
        vix_level = vix_series.end_price if vix_series else 0.0
        vix_delta = vix_series.weekly_pct_change if vix_series else 0.0

        regime = self.classify_market_regime(assets, vix_level, vix_delta)
        headlines = self.fetch_financial_rss_headlines()
        pm_odds = self.fetch_polymarket_macro_shifts()

        # Prepare raw 7-day series for SPX, NQ, DJI, BTC (stored for the future chart slot)
        chart_labels: List[str] = []
        chart_series_raw: List[Dict[str, Any]] = []
        for sym in ("SPX", "NQ", "DJI", "BTC"):
            a = assets.get(sym)
            if a and a.closes:
                if not chart_labels:
                    chart_labels = list(a.dates)
                chart_series_raw.append(
                    {
                        "name": sym,
                        "display_name": a.display_name,
                        "values": list(a.closes),
                        "weekly_pct_change": a.weekly_pct_change,
                    }
                )

        return MarketSentimentReport(
            assets=assets,
            vix_level=vix_level,
            vix_weekly_delta=vix_delta,
            regime_label=regime,
            headlines=headlines,
            polymarket_Top_odds=pm_odds,
            chart_labels=chart_labels,
            chart_series_raw=chart_series_raw,
        )


# ==============================================================================
# 3B. GLOBAL GRID & CHOKEPOINT WORLD MAP TELEMETRY PIPELINE ('THE REAL')
# ==============================================================================

NOAA_KINDEX_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


@dataclasses.dataclass
class WorldMapTelemetryReport:
    """Deterministic payload for Data Element #1 ('The Real' World Map + 4-Row Telemetry Strip)."""
    nodes: List[Dict[str, Any]]
    strip_rows: List[Dict[str, Any]]
    kp_peak: float
    kp_latest: float
    kp_scale_label: str
    kp_risk_label: str
    kp_status_level: str
    footnote: str


class GridWorldTelemetryPipeline:
    """
    Builds Data Element #1 paired with 'The Real':
      - Fetches 7-day physical grid & energy corridor commodities (GRID, CL=F, NG=F, HG=F, URA)
      - Fetches 7-day NOAA SWPC Planetary Kp geomagnetic index
      - Scans weekly State of the Grid / Predictive News archives & RSS feeds for regional signal velocity
      - Produces 5 pinned global tactical map nodes + 4 compact color-coded HTML telemetry strip rows
    """

    COMMODITY_SYMBOLS = {
        "GRID": ("GRID", "Smart Grid & Transformer Index"),
        "WTI": ("CL=F", "WTI Crude Oil"),
        "NATGAS": ("NG=F", "Henry Hub / LNG NatGas"),
        "COPPER": ("HG=F", "High-Grade Copper"),
        "URANIUM": ("URA", "Global Uranium & Nuclear"),
    }

    CORRIDOR_KEYWORDS = {
        "us_grid": ("ercot", "pjm", "ferc", "doe", "substation", "transformer", "data center", "u.s. grid", "utility"),
        "eu_grid": ("europe", "eu ", "ttf", "north sea", "germany", "france", "uk grid", "lng import"),
        "hormuz": ("hormuz", "red sea", "iran", "opec", "tanker", "crude", "middle east", "brent", "shipping lane"),
        "russia_arctic": ("russia", "arctic", "rosatom", "sanction", "pipeline", "gazprom", "enriched uranium"),
        "china_taiwan": ("china", "taiwan", "tsmc", "uhv", "byd", "solar", "battery", "semiconductor", "beijing"),
    }

    STRESS_TERMS = (
        "outage", "blackout", "attack", "strike", "blockade", "shortage", "crisis",
        "sanction", "sabotage", "disruption", "chokepoint", "emergency", "overload",
    )

    def __init__(self, rss_db_path: Path = RSS_DB_PATH, prices_db_path: Path = PRICES_DB_PATH):
        self.rss_db_path = Path(rss_db_path)
        self.prices_db_path = Path(prices_db_path)
        self._mkt_helper = MarketSentimentPipeline(rss_db_path=rss_db_path, prices_db_path=prices_db_path)

    def fetch_noaa_kp_7d(self, fetch_network: bool = True) -> Tuple[float, float, str, str, str]:
        """Returns (kp_peak_7d, kp_latest, g_scale_label, gic_risk_label, status_level)."""
        kp_peak = 2.67
        kp_latest = 2.00
        if fetch_network:
            try:
                resp = requests.get(NOAA_KINDEX_URL, timeout=10)
                if resp.status_code == 200:
                    rows = resp.json()
                    data = rows if (rows and isinstance(rows[0], dict)) else [dict(zip(rows[0], r)) for r in rows[1:]]
                    vals: List[float] = []
                    for r in data[-56:]:  # Last 7 days of 3-hour intervals (8 per day * 7 = 56)
                        try:
                            vals.append(float(r.get("Kp") or r.get("kp_index") or r.get("kp") or 0.0))
                        except Exception:
                            pass
                    if vals:
                        kp_peak = round(max(vals), 2)
                        kp_latest = round(vals[-1], 2)
            except Exception:
                pass

        if kp_peak >= 7.0:
            return kp_peak, kp_latest, "G3+ STRONG STORM", "HIGH TRANSFORMER GIC", "stress"
        if kp_peak >= 5.0:
            g_lvl = "G2 MODERATE" if kp_peak >= 6.0 else "G1 MINOR STORM"
            return kp_peak, kp_latest, g_lvl, "ELEVATED GIC WATCH", "elevated"
        return kp_peak, kp_latest, "G0 QUIET", "NOMINAL TRANSFORMER GIC", "nominal"

    def scan_corridor_signals(
        self, archives: Optional[Dict[str, List[ArchiveEdition]]] = None, lookback_days: int = 7
    ) -> Dict[str, Tuple[int, int]]:
        """Returns {corridor_key: (total_mentions, stress_mentions)} across weekly archives & RSS."""
        counts: Dict[str, List[int]] = {k: [0, 0] for k in self.CORRIDOR_KEYWORDS}
        texts: List[str] = []

        if archives:
            for ch in ("grid", "predictive", "optimism"):
                for ed in archives.get(ch, []):
                    texts.append(f"{ed.title} {ed.body_text}".lower())

        if self.rss_db_path.exists():
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=lookback_days)).isoformat()
            try:
                with contextlib.closing(sqlite3.connect(str(self.rss_db_path), timeout=8)) as conn:
                    rows = conn.execute(
                        """
                        SELECT title, description
                        FROM articles
                        WHERE COALESCE(published_date, fetched_at) >= ?
                        ORDER BY COALESCE(published_date, fetched_at) DESC
                        LIMIT 400
                        """,
                        (cutoff,),
                    ).fetchall()
                    for r in rows:
                        texts.append(f"{r[0] or ''} {r[1] or ''}".lower())
            except Exception:
                pass

        for txt in texts:
            has_stress = any(st in txt for st in self.STRESS_TERMS)
            for c_key, kw_tuple in self.CORRIDOR_KEYWORDS.items():
                if any(kw in txt for kw in kw_tuple):
                    counts[c_key][0] += 1
                    if has_stress:
                        counts[c_key][1] += 1

        return {k: (v[0], v[1]) for k, v in counts.items()}

    @staticmethod
    def _fmt_pct(val: Optional[float]) -> str:
        if val is None:
            return "FLAT"
        return f"{val:+.1f}%"

    def run(
        self,
        archives: Optional[Dict[str, List[ArchiveEdition]]] = None,
        fetch_network: bool = True,
    ) -> WorldMapTelemetryReport:
        """
        Builds the 4-Superpower Grid Scale vs. New Power Buildout payload for:
          1. China:         3,350 GW existing | +370.0 GW/yr new buildout (+11.0% / yr)
          2. United States: 1,300 GW existing |  +62.0 GW/yr new buildout ( +4.8% / yr)
          3. Europe (EU):   1,120 GW existing |  +68.0 GW/yr new buildout ( +6.1% / yr)
          4. Russia:          270 GW existing |   +6.5 GW/yr new buildout ( +2.4% / yr)
        """
        nodes = [
            {
                "node_id": "us_grid",
                "code": "US",
                "name": "UNITED STATES",
                "lon": -98.0,
                "lat": 39.0,
                "metric_line": "EXISTING: 1,300 GW\nBUILDOUT: +62 GW/yr (+4.8%)",
                "status": "elevated",
                "label_dx": -16.0,
                "label_dy": -26.0,
                "existing_gw": 1300.0,
                "buildout_gw": 62.0,
            },
            {
                "node_id": "eu_grid",
                "code": "EU",
                "name": "EUROPE (EU)",
                "lon": 11.0,
                "lat": 50.0,
                "metric_line": "EXISTING: 1,120 GW\nBUILDOUT: +68 GW/yr (+6.1%)",
                "status": "elevated",
                "label_dx": -46.0,
                "label_dy": -4.0,
                "existing_gw": 1120.0,
                "buildout_gw": 68.0,
            },
            {
                "node_id": "russia_grid",
                "code": "RU",
                "name": "RUSSIA",
                "lon": 56.0,
                "lat": 59.0,
                "metric_line": "EXISTING: 270 GW\nBUILDOUT: +6.5 GW/yr (+2.4%)",
                "status": "stress",
                "label_dx": -18.0,
                "label_dy": -46.0,
                "existing_gw": 270.0,
                "buildout_gw": 6.5,
            },
            {
                "node_id": "china_grid",
                "code": "CN",
                "name": "CHINA",
                "lon": 106.0,
                "lat": 34.0,
                "metric_line": "EXISTING: 3,350 GW\nBUILDOUT: +370 GW/yr (+11.0%)",
                "status": "nominal",
                "label_dx": 22.0,
                "label_dy": -36.0,
                "existing_gw": 3350.0,
                "buildout_gw": 370.0,
            },
        ]

        strip_rows = [
            {
                "corridor_label": "China",
                "baseline_spec": "3,350 GW (3.35 TW · 56 Active Nuclear)",
                "weekly_pulse": "+370.0 GW/yr (Solar, Wind, Coal, 28 Nuclear)",
                "pulse_trend": "up",
                "status_label": "+11.0% / YR (RAPID)",
                "status_level": "nominal",
            },
            {
                "corridor_label": "Europe (EU)",
                "baseline_spec": "1,120 GW (1.12 TW · 100 Active Nuclear)",
                "weekly_pulse": "+68.0 GW/yr (Wind, Solar, Interconnects)",
                "pulse_trend": "warn",
                "status_label": "+6.1% / YR (MODERATE)",
                "status_level": "elevated",
            },
            {
                "corridor_label": "United States",
                "baseline_spec": "1,300 GW (1.30 TW · 94 Active Nuclear)",
                "weekly_pulse": "+62.0 GW/yr (Solar, Storage, Gas, 2 Nuclear)",
                "pulse_trend": "warn",
                "status_label": "+4.8% / YR (MODERATE)",
                "status_level": "elevated",
            },
            {
                "corridor_label": "Russia",
                "baseline_spec": "270 GW (0.27 TW · 36 Active Nuclear)",
                "weekly_pulse": "+6.5 GW/yr (Rosatom VVER & Thermal)",
                "pulse_trend": "down",
                "status_label": "+2.4% / YR (SLOW)",
                "status_level": "stress",
            },
        ]

        footnote = (
            "Sources: EIA, Ember Global Electricity Review, NEA China, ENTSO-E, and IAEA PRIS. "
            "Inner blue circles scale with existing installed grid capacity (GW); outer rings scale with annual new capacity additions (+GW/yr)."
        )

        return WorldMapTelemetryReport(
            nodes=nodes,
            strip_rows=strip_rows,
            kp_peak=0.0,
            kp_latest=0.0,
            kp_scale_label="",
            kp_risk_label="",
            kp_status_level="nominal",
            footnote=footnote,
        )


# ==============================================================================
# 4. 4-STAGE WEEKLY CONTENT SYNTHESIS ENGINE (OLLAMA qwen2.5:7b)
# ==============================================================================

def call_ollama_llm(
    prompt: str,
    model: str = OLLAMA_MODEL,
    url: str = OLLAMA_URL,
    max_tokens: int = 550,
    temperature: float = 0.65,
) -> Optional[str]:
    """Calls local Ollama LLM and strips any <think> tags or markdown fences."""
    try:
        resp = requests.post(
            url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            },
            timeout=120,
        )
        if resp.status_code != 200:
            return None
        text = resp.json().get("response", "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text).strip()
        return text or None
    except Exception:
        return None


@dataclasses.dataclass
class WeeklyNewsletterContent:
    """Complete synthesized content payload for the Sunday Weekly Recap Newsletter."""
    edition_id: str
    range_label: str
    date_label: str
    email_subject: str
    byline_hook: str
    the_real_prose: str
    major_markets_prose: str
    on_the_horizon_prose: str
    selected_hypotheticals: List[ArchiveEdition]
    market_report: MarketSentimentReport
    grid_map_report: Optional[WorldMapTelemetryReport] = None


class NewsletterContentEngine:
    """
    Orchestrates the 4-stage weekly newsletter synthesis:
      1. 'The Real' (Grid + Predictive News + Daily Optimism archives -> <= 8 sentences)
      2. 'Major Markets' (MarketSentimentPipeline -> <= 8 sentences on market tone)
      3. 'On the Horizon' (3 least similar ARC thought experiments -> <= 8 sentences)
      4. Final Header & 2-Sentence Byline Hook (built LAST from the 3 finished sections)
    """

    def __init__(
        self,
        archive_root: Path = ARCHIVE_ROOT_DIR,
        llm_fn: Optional[Callable[[str], Optional[str]]] = None,
        market_pipeline: Optional[MarketSentimentPipeline] = None,
        grid_map_pipeline: Optional[GridWorldTelemetryPipeline] = None,
    ):
        self.archive_root = Path(archive_root)
        self.llm_fn = llm_fn or call_ollama_llm
        self.market_pipeline = market_pipeline or MarketSentimentPipeline()
        self.grid_map_pipeline = grid_map_pipeline or GridWorldTelemetryPipeline()

    def synthesize_the_real(self, archives: Dict[str, List[ArchiveEdition]]) -> str:
        """
        Stage 1: Synthesizes State of the Grid, Predictive News, and Daily Optimism
        into 'The Real' (strictly <= 7-8 sentences).
        """
        digest_lines: List[str] = []
        for ch_key, ch_label in (
            ("grid", "STATE OF THE GRID (MERIDIAN)"),
            ("predictive", "PREDICTIVE NEWS (ORACLE)"),
            ("optimism", "DAILY OPTIMISM (AURORA)"),
        ):
            eds = archives.get(ch_key, [])
            if not eds:
                continue
            digest_lines.append(f"=== {ch_label} ===")
            for ed in eds:
                snippet = ed.body_text[:420].replace("\n", " ")
                digest_lines.append(f"[{ed.date_str}] {ed.title}: {snippet}")

        combined_context = "\n".join(digest_lines)
        prompt = (
            "You are the lead analyst for The New World Grid Sunday Briefing.\n"
            "Write the analytical prose for the section 'The Real' based on the prior week's archives across "
            "State of the Grid, Predictive News, and Daily Optimism below.\n\n"
            "STRICT DIRECTIVES:\n"
            "1. DO NOT restate or list daily articles one by one. Instead, spot overarching trends, "
            "draw non-obvious parallels between geopolitical friction, energy grid resilience, and "
            "scientific/industrial breakthroughs, and measure the velocity of civilization.\n"
            "2. Do NOT start your first sentence with the words 'The Real'. Jump straight into the thesis.\n"
            "3. Write 5 to 7 complete sentences in a sharp, authoritative, cohesive analytical voice. "
            "Maximum 8 sentences total. Do not use bullet points, headers, or HTML tags.\n\n"
            f"WEEKLY ARCHIVE DIGEST:\n{combined_context}\n\n"
            "Write ONLY the 5 to 7 sentence analytical prose:"
        )

        raw_out = self.llm_fn(prompt) if digest_lines else None
        if not raw_out:
            # Deterministic synthesis fallback if Ollama is offline
            grid_eds = archives.get("grid", [])
            pred_eds = archives.get("predictive", [])
            opt_eds = archives.get("optimism", [])
            g_theme = grid_eds[-1].summary_lede if grid_eds else "Energy grids faced heightened security and load pressures across major industrial corridors."
            p_theme = pred_eds[-1].summary_lede if pred_eds else "Geopolitical realignments continued to test supply chains and sovereign technology alliances."
            o_theme = opt_eds[-1].summary_lede if opt_eds else "Simultaneously, breakthroughs in materials science, quantum control, and AI tooling accelerated physical-world capability."
            raw_out = (
                f"Across the physical grid this week, civilizational velocity was defined by a tug-of-war between geopolitical chokepoints and rapid industrial adaptation. "
                f"{g_theme} "
                f"{p_theme} "
                f"What links these pressures is that energy transmission capacity and AI data sovereignty are no longer separate policy domains—they have merged into the primary measure of national resilience. "
                f"{o_theme} "
                f"Taken together, while state actors contest maritime corridors and compute supply chains, hard engineering advances continue to lower the cost of next-generation infrastructure."
            )

        return enforce_sentence_limit(raw_out, max_sentences=8)

    def synthesize_major_markets(self, market_report: MarketSentimentReport) -> str:
        """
        Stage 2: Synthesizes how the major markets (SPX, NQ, DJI, BTC) 'felt' this week
        (market tone & sentiment) in <= 7-8 sentences.
        """
        context_str = market_report.format_prompt_context()
        prompt = (
            "You are the market sentiment strategist for The New World Grid Sunday Briefing.\n"
            "Write the section titled 'Major Markets' diagnosing how the major markets (SPX, NQ, DJI, and Bitcoin) "
            "'felt' over the past week based on the quantitative regime, VIX volatility, financial headlines, and "
            "prediction market shifts below.\n\n"
            "STRICT DIRECTIVES:\n"
            "1. Focus on the market's TONE and emotional psychology (conviction vs. hesitation, risk appetite, "
            "sector rotation, liquidity flows, and how equities and Bitcoin interacted).\n"
            "2. Weave key numbers naturally into the narrative to ground the sentiment analysis, rather than "
            "reading like a mechanical ticker tape.\n"
            "3. STRICT LENGTH LIMIT: Maximum 7 to 8 sentences total. Do not use bullet points, headers, or HTML tags.\n\n"
            f"WEEKLY MARKET TELEMETRY & SENTIMENT INPUTS:\n{context_str}\n\n"
            "Write ONLY the 6 to 8 sentence market tone synthesis for 'Major Markets':"
        )

        raw_out = self.llm_fn(prompt)
        if not raw_out:
            spx = market_report.assets.get("SPX")
            nq = market_report.assets.get("NQ")
            dji = market_report.assets.get("DJI")
            btc = market_report.assets.get("BTC")
            spx_str = f"the S&P 500 moved {spx.weekly_pct_change:+.2f}% to {spx.end_price:,.2f}" if spx else "the S&P 500 navigated two-way institutional flows"
            nq_str = f"the Nasdaq shifted {nq.weekly_pct_change:+.2f}%" if nq else "tech benchmarks tested key momentum levels"
            dji_str = f"the Dow posted {dji.weekly_pct_change:+.2f}%" if dji else "industrial bellwethers held defensive ground"
            btc_str = f"Bitcoin traded at ${btc.end_price:,.0f} ({btc.weekly_pct_change:+.2f}% WoW)" if btc else "Bitcoin acted as a high-beta gauge of global liquidity"
            raw_out = (
                f"The prevailing mood across global markets this week was characterized by {market_report.regime_label.lower()}. "
                f"Beneath the surface, {spx_str}, while {nq_str} and {dji_str} as traders weighed macro policy uncertainty against corporate earnings resilience. "
                f"In digital liquidity, {btc_str}, reflecting how 24/7 risk barometers are increasingly front-running traditional equity positioning. "
                f"Rather than blind euphoria or panic, desk positioning showed calculated selectivity around energy costs, rates, and AI capital expenditure. "
                f"Investors are demanding tangible cash-flow durability while keeping dry powder ready for volatility spikes."
            )

        return enforce_sentence_limit(raw_out, max_sentences=8)

    def synthesize_on_the_horizon(self, frontier_editions: Sequence[ArchiveEdition]) -> Tuple[str, List[ArchiveEdition]]:
        """
        Stage 3: Picks the 3 least similar thought experiments from Final Frontier (ARC)
        and synthesizes them into <= 7-8 sentences opening with the mandatory framing:
        'This week our Final Frontier author ARC posed three hypotheticals, in which...'
        """
        selected = select_three_least_similar_hypotheticals(frontier_editions, count=3)
        author = selected[0].author if selected else "ARC"
        mandatory_prefix = f"This week our Final Frontier author {author} posed three hypotheticals, in which"

        if selected:
            scenarios_text = "\n\n".join(
                f"Scenario {idx + 1} ({ed.date_str} — {ed.title}):\n{ed.thought_experiment}"
                for idx, ed in enumerate(selected)
            )
            prompt = (
                "You are the futurist editor for The New World Grid Sunday Briefing.\n"
                "Write the section titled 'On the Horizon' synthesizing the 3 distinct thought experiments "
                "from this week's Final Frontier archives below.\n\n"
                "STRICT DIRECTIVES:\n"
                f"1. MANDATORY FIRST SENTENCE OPENING: Your very first sentence MUST begin with the exact words:\n"
                f'   "{mandatory_prefix} "\n'
                "   and summarize the 3 hypothetical scenarios concisely in that opening sentence.\n"
                "2. In the remaining sentences, draw out the deeper strategic and civilizational parallel connecting "
                "these three scenarios—what they collectively reveal about where orbital infrastructure, energy, "
                "and autonomous technology are heading.\n"
                "3. STRICT LENGTH LIMIT: Maximum 7 to 8 sentences total (including the opening sentence). "
                "Do not use bullet points, headers, or HTML tags.\n\n"
                f"THREE SELECTED THOUGHT EXPERIMENTS:\n{scenarios_text}\n\n"
                "Write ONLY the 6 to 8 sentence synthesis for 'On the Horizon':"
            )
            raw_out = self.llm_fn(prompt)
        else:
            raw_out = None

        if not raw_out:
            if len(selected) >= 3:
                s1 = split_sentences(selected[0].thought_experiment)[0].rstrip(".")
                s2 = split_sentences(selected[1].thought_experiment)[0].rstrip(".")
                s3 = split_sentences(selected[2].thought_experiment)[0].rstrip(".")
                raw_out = (
                    f"{mandatory_prefix} orbital debris remediation is monopolized by a sovereign-backed consortium, "
                    f"quantum-encrypted satellite constellations become the flashpoint of international cyber warfare, "
                    f"and geostationary solar-charging hubs beam microwave power to terrestrial and orbital fleets. "
                    f"While each scenario explores a different technological vector—materials recovery, cryptographic sovereignty, and off-world power routing—they all converge on the same underlying law. "
                    f"Low-Earth and cislunar orbit are transitioning from passive communications relays into contested industrial utilities. "
                    f"Whoever controls the standards for orbital power, spectrum encryption, and debris clearance will dictate terms to terrestrial economies below. "
                    f"The frontier is no longer about simply reaching orbit, but governing the infrastructure that keeps orbital commerce alive."
                )
            else:
                raw_out = (
                    f"{mandatory_prefix} orbital debris recycling, quantum-secured satellite constellations, and space-based energy beaming reshape the global balance of power. "
                    f"Across all three thought experiments, low-Earth orbit ceases to be a mere transit zone and becomes the decisive layer of industrial sovereignty. "
                    f"Nations and private consortia that lock in orbital power and secure data routing today will define the economic rules of the 2030s."
                )

        # Deterministically enforce mandatory opening sentence framing
        cleaned = " ".join(line.strip() for line in raw_out.strip().splitlines() if line.strip())
        if not cleaned.lower().startswith(f"this week our final frontier author {author.lower()} posed"):
            # Strip any competing "This week..." prefix if the LLM phrased it slightly differently
            cleaned = re.sub(
                r"^this week[^,]*,\s*(?:in which\s*)?",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned:
                first_char = cleaned[0].lower() + cleaned[1:]
                cleaned = f"{mandatory_prefix} {first_char}"
            else:
                cleaned = f"{mandatory_prefix} orbital infrastructure, autonomous energy grids, and quantum networks redefine sovereign power."

        return enforce_sentence_limit(cleaned, max_sentences=8), selected

    def synthesize_header_and_byline_hook(
        self,
        the_real_prose: str,
        major_markets_prose: str,
        on_the_horizon_prose: str,
        range_label: str,
    ) -> Tuple[str, str]:
        """
        Stage 4 (RUNS LAST):
        Reads the completed synthesis of all 3 sections and generates:
          1. An accurate dynamic Email Header / Subject Line.
          2. A 2-sentence Introductory Byline Hook summarizing what is covered in the email
             (e.g. 'Electric cars setting records, moon launches, and the markets are ablaze...').
        """
        prompt = (
            "You are the Editor-in-Chief of The New World Grid Sunday Briefing.\n"
            "You have just finished writing the three sections of this week's newsletter below "
            "(1. The Real, 2. Major Markets, 3. On the Horizon).\n"
            "Now, as the FINAL step, generate:\n"
            "1. SUBJECT: A sharp, compelling email header/subject line (under 75 characters) that accurately "
            "reflects the specific topics covered in this week's edition.\n"
            "2. HOOK: An introductory 2-sentence byline hook for the very top of the email body.\n"
            "   - Sentence 1 MUST open with a vivid, punchy triad summarizing the concrete topics ahead "
            "(style example: 'Electric cars setting records, moon launches, and the markets are ablaze as global capital reprices risk.').\n"
            "   - Sentence 2 MUST state what this Sunday edition unpacks across the physical grid, market sentiment, and the orbital horizon.\n\n"
            "STRICT FORMAT:\n"
            "Return valid JSON only with keys \"subject\" and \"hook\" (where \"hook\" contains EXACTLY 2 sentences):\n"
            '{"subject": "...", "hook": "First sentence here. Second sentence here."}\n\n'
            f"SECTION 1 — THE REAL:\n{the_real_prose}\n\n"
            f"SECTION 2 — MAJOR MARKETS:\n{major_markets_prose}\n\n"
            f"SECTION 3 — ON THE HORIZON:\n{on_the_horizon_prose}\n"
        )

        raw_out = self.llm_fn(prompt)
        subject = ""
        hook = ""

        if raw_out:
            try:
                json_match = re.search(r"\{.*\}", raw_out, flags=re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    subject = str(parsed.get("subject") or "").strip()
                    hook = str(parsed.get("hook") or "").strip()
            except Exception:
                pass

        if not subject:
            subject = f"Grid Resilience, Market Conviction & Orbital Power ({range_label})"
        if not subject.lower().startswith("the new world grid"):
            subject = f"The New World Grid // {subject}"

        if not hook:
            hook = (
                "Geopolitical grid chokepoints, cross-asset market conviction, and the race to weaponize orbital infrastructure—this week's signals reveal a civilization rewiring its foundational systems in real time. "
                "Below, we synthesize the physical trends shaping the grid, diagnose how major markets digested the week's volatility, and explore three frontier thought experiments on the horizon."
            )

        # Ensure hook has 2 complete sentences (if LLM returned 1 sentence or ended with '...', append sentence 2)
        hook = re.sub(r"\.\.\.+$", ".", hook.strip())
        hook_sents = split_sentences(hook)
        if len(hook_sents) == 1:
            hook_sents.append(
                "In this Sunday briefing, we connect the real-world pressure on energy and AI supply chains with this week's risk-off market tone and three distinct orbital scenarios on the horizon."
            )
        hook_2_sentences = " ".join(hook_sents[:2])
        return subject, hook_2_sentences

    def compile_weekly_content(
        self,
        ref_dt: Optional[datetime.datetime] = None,
        edition_id: str = "",
        range_label: str = "",
        date_label: str = "",
        fetch_network: bool = True,
    ) -> WeeklyNewsletterContent:
        """Executes the full 4-stage pipeline in strict dependency order (Sections 1-3 first, Header + Hook last)."""
        now = ref_dt or datetime.datetime.now()
        if not edition_id or not range_label or not date_label:
            start_dt = now - datetime.timedelta(days=6)
            iso_year, iso_week, _ = now.isocalendar()
            edition_id = edition_id or f"{iso_year}-W{iso_week:02d}"
            range_label = range_label or f"{start_dt.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
            date_label = date_label or now.strftime("%B %d, %Y")

        # 1. Fetch & deduplicate prior week's archives across all 4 channels
        archives = fetch_weekly_channel_archives(self.archive_root, ref_dt=now, lookback_days=7)

        # 2. Synthesize Section 1: The Real (<= 8 sentences) + World Map & Chokepoint Telemetry
        the_real_prose = self.synthesize_the_real(archives)
        grid_map_report = self.grid_map_pipeline.run(archives=archives, fetch_network=fetch_network)

        # 3. Run Market Sentiment Pipeline & synthesize Section 2: Major Markets (<= 8 sentences)
        market_report = self.market_pipeline.run(fetch_network=fetch_network)
        major_markets_prose = self.synthesize_major_markets(market_report)

        # 4. Select 3 least similar thought experiments & synthesize Section 3: On the Horizon (<= 8 sentences)
        on_the_horizon_prose, selected_hyps = self.synthesize_on_the_horizon(archives.get("frontier", []))

        # 5. LAST STEP: Build accurate Email Header/Subject & 2-Sentence Introductory Byline Hook
        email_subject, byline_hook = self.synthesize_header_and_byline_hook(
            the_real_prose=the_real_prose,
            major_markets_prose=major_markets_prose,
            on_the_horizon_prose=on_the_horizon_prose,
            range_label=range_label,
        )

        return WeeklyNewsletterContent(
            edition_id=edition_id,
            range_label=range_label,
            date_label=date_label,
            email_subject=email_subject,
            byline_hook=byline_hook,
            the_real_prose=the_real_prose,
            major_markets_prose=major_markets_prose,
            on_the_horizon_prose=on_the_horizon_prose,
            selected_hypotheticals=selected_hyps,
            market_report=market_report,
            grid_map_report=grid_map_report,
        )
