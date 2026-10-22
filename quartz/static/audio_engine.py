#!/usr/bin/env python3
r"""
==============================================================================
[aeOS:Home:Audio]
Script / Service: audio_engine.py
Path: C:\Users\bertb\new-world-grid\quartz\static\audio_engine.py
Role & Mission: Synthesizes the daily New World Grid master audio podcast
                (index_master_summary.wav) using Ollama (qwen2.5:7b) and
                Kokoro TTS (am_michael), enforcing a distinct multi-second
                silence gap, broadcast transition chime, spoken section cue,
                and post-disclaimer pause before the closing fictional
                "What follows is purely a thought experiment." segment.
==============================================================================
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf
from kokoro import KPipeline


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
DEFAULT_MODEL = os.environ.get("AUDIO_OLLAMA_MODEL", "qwen2.5:7b")
DEFAULT_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
DEFAULT_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))
SAMPLE_RATE = 24000
PLAYER_MARKER = "NWG_AUDIO_PLAYER"
SCRIPT_WORD_TARGET = "280 to 350 words"
DATE_STAMP = datetime.now().strftime("%b %d").upper()

# Pause & Cue timing constants for the closing "Thought Experiment" fictional section
PRE_CUE_SILENCE_SECONDS = 2.2
POST_CHIME_SILENCE_SECONDS = 0.5
MID_DISCLAIMER_SILENCE_SECONDS = 0.7
POST_DISCLAIMER_SILENCE_SECONDS = 1.5
DISCLAIMER_SPEED_FACTOR = 0.94
THOUGHT_EXPERIMENT_HEADER = "Final section: Frontier Speculation."
THOUGHT_EXPERIMENT_DISCLAIMER = "What follows is purely a thought experiment."


@dataclass(frozen=True)
class BroadcastTarget:
    markdown_path: Path
    audio_filename: str
    summary_title: str
    persona: str
    prompt_scope: str
    include_other_pages: bool = False

    @property
    def audio_url(self) -> str:
        return f"/assets/audio/{self.audio_filename}"


def build_targets(repo_root: Path) -> list[BroadcastTarget]:
    content_dir = repo_root / "content"
    return [
        BroadcastTarget(
            markdown_path=content_dir / "index.md",
            audio_filename="index_master_summary.wav",
            summary_title="🌐 New World Grid",
            persona="New World Grid Host",
            prompt_scope=(
                "Create a comprehensive, informative, and analytical synthesis of today's factual "
                "findings across all grid pages (Predictive News, Daily Optimism, State of the Grid, "
                "and Final Frontier: The High Ground and The EV Race). Weave them into a single "
                "coherent monologue."
            ),
            include_other_pages=True,
        ),
    ]


def parse_args() -> argparse.Namespace:
    default_repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Generate Quartz broadcast audio and inject a custom player."
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo_root)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    targets = build_targets(repo_root)
    audio_dir = repo_root / "content" / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if not all(target.markdown_path.exists() for target in targets):
        missing = [str(target.markdown_path) for target in targets if not target.markdown_path.exists()]
        raise SystemExit(f"Missing Markdown files:\n- " + "\n- ".join(missing))

    source_cache = {target.markdown_path: target.markdown_path.read_text(encoding="utf-8") for target in targets}
    plain_text_cache = {
        path: normalize_source_for_prompt(content)
        for path, content in source_cache.items()
    }

    thought_experiment_text = extract_thought_experiment(repo_root)

    pipeline = None if args.dry_run else KPipeline(lang_code="a")
    generated_scripts: dict[str, str] = {}
    duration_manifest: dict[str, str] = {}

    for target in targets:
        prompt = build_prompt(target, targets, plain_text_cache)
        real_news_script = generate_script_via_ollama(model=args.model, prompt=prompt)
        real_news_script = strip_thought_experiment_from_script(real_news_script)
        real_news_script = ensure_opening_intro(real_news_script)

        if target.include_other_pages and thought_experiment_text:
            full_manifest_script = (
                f"{real_news_script} "
                f"[PAUSE {PRE_CUE_SILENCE_SECONDS:.1f}s + CHIME + PAUSE {POST_CHIME_SILENCE_SECONDS:.1f}s] "
                f"{THOUGHT_EXPERIMENT_HEADER} "
                f"[PAUSE {MID_DISCLAIMER_SILENCE_SECONDS:.1f}s] "
                f"{THOUGHT_EXPERIMENT_DISCLAIMER} "
                f"[PAUSE {POST_DISCLAIMER_SILENCE_SECONDS:.1f}s] "
                f"{thought_experiment_text}"
            )
        else:
            full_manifest_script = real_news_script

        generated_scripts[target.audio_filename] = full_manifest_script

        if args.dry_run:
            duration_label = "01:00"
        else:
            output_path = audio_dir / target.audio_filename
            duration_label = synthesize_audio(
                pipeline=pipeline,
                text=real_news_script,
                voice=args.voice,
                speed=args.speed,
                output_path=output_path,
                thought_experiment_text=thought_experiment_text if target.include_other_pages else "",
            )
        duration_manifest[target.audio_filename] = duration_label

    audit_payload = {
        "generatedAt": datetime.now().isoformat(),
        "model": args.model,
        "voice": args.voice,
        "speed": args.speed,
        "pauseConfig": {
            "preCueSilenceSeconds": PRE_CUE_SILENCE_SECONDS,
            "postChimeSilenceSeconds": POST_CHIME_SILENCE_SECONDS,
            "midDisclaimerSilenceSeconds": MID_DISCLAIMER_SILENCE_SECONDS,
            "postDisclaimerSilenceSeconds": POST_DISCLAIMER_SILENCE_SECONDS,
            "disclaimerSpeedFactor": DISCLAIMER_SPEED_FACTOR,
        },
        "scripts": generated_scripts,
        "durations": duration_manifest,
    }
    if not args.dry_run:
        audit_path = audio_dir / "broadcast_manifest.json"
        audit_path.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")

    print("Audio broadcast engine complete.")
    for target in targets:
        print(f"- {target.markdown_path.name} -> {target.audio_url} ({duration_manifest[target.audio_filename]})")
    return 0


def strip_archive_and_boilerplate(raw_text: str) -> str:
    """Strips archive backlog cards, byline headers, and jump links so only today's live text remains."""
    text = raw_text
    # Cut off everything starting at EDITION_ARCHIVE_BACKLOG
    text = re.split(r"<!--\s*EDITION_ARCHIVE_BACKLOG\s*-->", text, maxsplit=1)[0]
    # Remove byline blocks, author attribution spans, section date headers, and jump buttons
    text = re.sub(r"<div class=\"sotg-byline\">.*?</div>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<span class=\"meridian-attr\">.*?</span>", " ", text, flags=re.DOTALL)
    text = re.sub(r"##\s+Daily Intelligence Brief[^\r\n]*", " ", text)
    text = re.sub(r"<!--\s*NEWS_HUNTER_JUMP\s*-->.*?<!--\s*/NEWS_HUNTER_JUMP\s*-->", " ", text, flags=re.DOTALL)
    # Remove Breaking trends in AI GitHub repo links list at bottom of Optimism.md
    text = re.split(r"###\s+Breaking trends in AI today", text, maxsplit=1)[0]
    return text


def strip_thought_experiment_from_markdown(raw_text: str) -> str:
    """Removes the closing Thought Experiment section from Final-Frontier.md before real-news synthesis."""
    text = strip_archive_and_boilerplate(raw_text)
    text = re.split(
        r"(?:###\s*\*\*Frontier Speculation|\*?\s*What follows is purely a thought experiment\.)",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return text


def extract_thought_experiment(repo_root: Path) -> str:
    """
    Extracts the closing 'What follows is purely a thought experiment.' narrative
    from content/Final-Frontier.md and cleans it into spoken prose without truncation.
    """
    frontier_path = repo_root / "content" / "Final-Frontier.md"
    if not frontier_path.exists():
        return ""

    raw = frontier_path.read_text(encoding="utf-8")
    raw = strip_archive_and_boilerplate(raw)
    raw = re.split(r"<!--\s*/?FRONTIER_ENGINE_END\s*-->", raw, maxsplit=1)[0]

    match = re.search(
        r"(?:\*|_)?What follows is purely a thought experiment\.?(?:\*|_)?\s*(.+)",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""

    scenario = match.group(1).strip()
    scenario = re.sub(r"<!--.*?-->", " ", scenario, flags=re.DOTALL)
    scenario = re.sub(r"<[^>]+>", " ", scenario)
    scenario = html.unescape(scenario)
    scenario = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", scenario)
    scenario = re.sub(r"[*_>#`]+", " ", scenario)
    scenario = re.sub(r"\s+", " ", scenario).strip()
    return scenario


def strip_thought_experiment_from_script(script_text: str) -> str:
    """Guarantees the LLM real-news monologue does not prematurely include the thought experiment."""
    parts = re.split(
        r"(?:What follows is purely a thought experiment\.?|In a thought experiment,|Frontier Speculation:)",
        script_text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    return parts[0].strip()


def ensure_opening_intro(script_text: str) -> str:
    """
    Guarantees the broadcast opens with a grounded 'Today on New World Grid,' intro
    and never starts mid-thought with a transition phrase like 'Moving to...' or 'Moving into...'.
    """
    cleaned = script_text.strip()
    if not cleaned:
        return cleaned

    # Strip any accidental leading mid-stream transition phrase at 00:00
    cleaned = re.sub(
        r"^(?:Moving\s+(?:to|into)\s+[^,]+,\s*|Turning\s+to\s+[^,]+,\s*|Next,\s*)",
        "",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    ).strip()

    # If the model already opened with 'Today on New World Grid' or 'Today's findings across New World Grid', keep it
    if re.match(r"^Today(?:'s|\u2019s)?\s+(?:on|across|in)\s+(?:the\s+)?New World Grid", cleaned, flags=re.IGNORECASE):
        return cleaned

    # Lowercase the first word only if it's a common article/word (preserve acronyms & proper nouns)
    first_word = cleaned.split(" ", 1)[0].rstrip(",.:;")
    lowercase_starters = {"The", "In", "Across", "Recent", "New", "Global", "Multiple", "Significant", "Decentralized", "Geopolitical", "While", "Meanwhile"}
    if first_word in lowercase_starters:
        cleaned = cleaned[0].lower() + cleaned[1:]

    return f"Today on New World Grid, {cleaned}"


def normalize_source_for_prompt(raw_text: str) -> str:
    text = strip_archive_and_boilerplate(raw_text)
    text = re.sub(r"^---\s*\r?\n.*?^\-\-\-\s*\r?\n?", "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"`{3,}.*?`{3,}", " ", text, flags=re.DOTALL)
    text = text.replace("&mdash;", "-").replace("&nbsp;", " ")
    text = html.unescape(text)
    text = re.sub(r"!\[\[.*?\]\]", " ", text)
    text = re.sub(r"\[\[(.*?)\]\]", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"[*_>#-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


def build_prompt(
    target: BroadcastTarget,
    all_targets: Iterable[BroadcastTarget],
    plain_text_cache: dict[Path, str],
) -> str:
    if target.include_other_pages:
        sections = []
        repo_root = target.markdown_path.resolve().parents[1]
        content_dir = repo_root / "content"
        others = ["Predictive-News.md", "Optimism.md", "State-of-the-Grid.md", "Final-Frontier.md"]
        for o in others:
            p = content_dir / o
            if p.exists():
                raw_page = p.read_text(encoding="utf-8")
                if o == "Final-Frontier.md":
                    raw_page = strip_thought_experiment_from_markdown(raw_page)
                txt = normalize_source_for_prompt(raw_page)
                sections.append(f"{o.replace('.md', '')}:\n{txt[:2500]}")
        body = "\n\n".join(sections)
    else:
        body = plain_text_cache[target.markdown_path]

    return (
        "You are writing an informative monologue for New World Grid.\n"
        f"Persona: {target.persona}\n"
        f"Objective: {target.prompt_scope}\n"
        "Tone and Style Guidelines:\n"
        "- Voice: Conversational and casual, yet remains analytical and unbiased. Speak as a colleague sharing a clear, indifferent summary of facts—knowledgeable but not performing.\n"
        "- Begin the broadcast with the exact opening phrase: 'Today on New World Grid,' followed immediately by the first analytical point from Predictive News.\n"
        "- Cover all four desks in order: Predictive News, Daily Optimism, State of the Grid, and Final Frontier (The High Ground and The EV Race).\n"
        "- NEVER start the first sentence with a mid-stream transition phrase such as 'Moving to...' or 'Moving into...'. Reserve natural transitions (e.g., 'On the optimism front,', 'Turning to the State of the Grid,', 'In the Final Frontier,') strictly for moving between the subsequent desks.\n"
        "- Synthesize the key takeaways concisely rather than reading every paragraph verbatim, and mention the geomagnetic Kp index only once.\n"
        "- DO NOT include any fictional 'thought experiment' or '2036' scenario; cover ONLY the real-news reporting.\n"
        "- DO NOT use high-stakes, dramatic, or sensationalist language.\n"
        "- Do not say 'Hello', 'Welcome', 'Breaking news', or 'Signing off'.\n"
        "- No author names or meta-commentary about the text itself (e.g., 'the author states', 'this page shows').\n"
        "- You may mention 'New World Grid' and the specific page title when relevant to the context.\n"
        "- Use clean spoken prose only. No bullet points, stage directions, or markdown symbols.\n"
        f"- Length: Target {SCRIPT_WORD_TARGET} for a natural reading pace. Always finish your final sentence completely.\n"
        "- Focus on clarity and the synthesis of signals.\n\n"
        "Source material:\n"
        f"{body}\n\n"
        "CRITICAL: Return ONLY the spoken text. Do not include labels, descriptions, or commentary."
    )


def generate_script_via_ollama(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.65,
            "top_p": 0.92,
            "num_predict": 1200,
        },
    }
    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama request failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            "Could not reach Ollama. Start the local server and ensure it is listening on "
            f"{OLLAMA_URL}."
        ) from exc

    script_text = clean_script_text(data.get("response", ""))
    if not script_text:
        raise RuntimeError("Ollama returned an empty script.")
    return script_text


def clean_script_text(text: str) -> str:
    cleaned = text.strip().strip('"').strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def generate_silence(seconds: float) -> np.ndarray:
    """Generates explicit zero-amplitude float32 PCM silence for the given duration."""
    num_samples = max(int(round(seconds * SAMPLE_RATE)), 0)
    return np.zeros(num_samples, dtype=np.float32)


def generate_transition_chime(peak_amplitude: float = 0.065) -> np.ndarray:
    """
    Generates a subtle, low-key two-note broadcast transition chime (A4 -> E4 gentle fifth drop)
    with raised-cosine attack and exponential decay so listeners clearly perceive the shift
    from factual reporting to the closing thought experiment.
    """
    note1_dur = 0.20
    gap_dur = 0.05
    note2_dur = 0.28

    def _tone(freq: float, dur: float, amp: float) -> np.ndarray:
        n = int(round(dur * SAMPLE_RATE))
        t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
        wave = np.sin(2.0 * np.pi * freq * t) + 0.25 * np.sin(2.0 * np.pi * (freq * 2.0) * t)
        # Smooth 20ms attack + exponential decay
        attack_n = max(int(0.02 * SAMPLE_RATE), 1)
        env = np.exp(-5.5 * (t / dur)).astype(np.float32)
        env[:attack_n] *= np.linspace(0.0, 1.0, attack_n, dtype=np.float32)
        env[-attack_n:] *= np.linspace(1.0, 0.0, attack_n, dtype=np.float32)
        return (wave * env * amp).astype(np.float32)

    tone1 = _tone(528.0, note1_dur, peak_amplitude)
    gap = generate_silence(gap_dur)
    tone2 = _tone(396.0, note2_dur, peak_amplitude * 0.9)
    return np.concatenate([tone1, gap, tone2])


def _tts_chunks(pipeline: KPipeline, text: str, voice: str, speed: float) -> list[np.ndarray]:
    """Synthesizes a text segment via Kokoro TTS and returns float32 audio chunks."""
    chunks: list[np.ndarray] = []
    if not text or not text.strip():
        return chunks
    for _, _, audio in pipeline(text.strip(), voice=voice, speed=speed):
        chunks.append(np.asarray(audio, dtype=np.float32))
    return chunks


def synthesize_audio(
    pipeline: KPipeline,
    text: str,
    voice: str,
    speed: float,
    output_path: Path,
    thought_experiment_text: str = "",
) -> str:
    """
    Synthesizes the full broadcast audio file.
    If thought_experiment_text is provided (or if 'What follows is purely a thought experiment.'
    is embedded in `text`), inserts:
      1. PRE_CUE_SILENCE_SECONDS (2.2s) of pure PCM silence after real news ends
      2. A subtle broadcast transition chime + POST_CHIME_SILENCE_SECONDS (0.5s) silence
      3. Spoken section cue ('Final section: Frontier Speculation.') + 0.7s silence
      4. Spoken disclaimer ('What follows is purely a thought experiment.') at deliberate pace
      5. POST_DISCLAIMER_SILENCE_SECONDS (1.5s) of pure PCM silence
      6. The fictional thought-experiment narrative
    """
    main_text = text.strip()
    te_body = thought_experiment_text.strip()

    # Fallback: if thought_experiment_text wasn't passed separately but exists inside `text`
    if not te_body and re.search(r"What follows is purely a thought experiment\.?", main_text, re.IGNORECASE):
        split_parts = re.split(
            r"What follows is purely a thought experiment\.?",
            main_text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        main_text = split_parts[0].strip()
        te_body = split_parts[1].strip() if len(split_parts) > 1 else ""

    audio_chunks: list[np.ndarray] = []
    audio_chunks.extend(_tts_chunks(pipeline, main_text, voice=voice, speed=speed))

    if te_body:
        disclaimer_speed = max(0.85, round(speed * DISCLAIMER_SPEED_FACTOR, 2))
        # 1. Pre-section silence gap after real news concludes
        audio_chunks.append(generate_silence(PRE_CUE_SILENCE_SECONDS))
        # 2. Subtle sonic transition cue + post-chime pause
        audio_chunks.append(generate_transition_chime())
        audio_chunks.append(generate_silence(POST_CHIME_SILENCE_SECONDS))
        # 3. Spoken section boundary header
        audio_chunks.extend(_tts_chunks(pipeline, THOUGHT_EXPERIMENT_HEADER, voice=voice, speed=disclaimer_speed))
        audio_chunks.append(generate_silence(MID_DISCLAIMER_SILENCE_SECONDS))
        # 4. Spoken disclaimer phrase
        audio_chunks.extend(_tts_chunks(pipeline, THOUGHT_EXPERIMENT_DISCLAIMER, voice=voice, speed=disclaimer_speed))
        # 5. Deliberate post-disclaimer silence gap before fictional narrative begins
        audio_chunks.append(generate_silence(POST_DISCLAIMER_SILENCE_SECONDS))
        # 6. Thought experiment fictional scenario body
        audio_chunks.extend(_tts_chunks(pipeline, te_body, voice=voice, speed=speed))

    if not audio_chunks:
        raise RuntimeError(f"No audio chunks were generated for {output_path.name}.")

    combined = np.concatenate(audio_chunks)
    sf.write(str(output_path), combined, SAMPLE_RATE)
    duration_seconds = len(combined) / SAMPLE_RATE
    return format_duration(duration_seconds)


def format_duration(total_seconds: float) -> str:
    whole_seconds = max(int(round(total_seconds)), 1)
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
