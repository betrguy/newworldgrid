#!/usr/bin/env python3
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
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "mannix/llama3.1-8b-abliterated")
DEFAULT_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
DEFAULT_SPEED = float(os.environ.get("KOKORO_SPEED", "0.94"))
SAMPLE_RATE = 24000
PLAYER_MARKER = "NWG_AUDIO_PLAYER"
SCRIPT_WORD_TARGET = "130 to 160 words"
DATE_STAMP = datetime.now().strftime("%b %d").upper()


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
            summary_title=f"MASTER BROADCAST // {DATE_STAMP}",
            persona="ANCHOR PRIME",
            prompt_scope="Create a homepage master summary that covers the signal from all four desk pages.",
            include_other_pages=True,
        ),
        BroadcastTarget(
            markdown_path=content_dir / "Predictive-News.md",
            audio_filename="predictive_news.wav",
            summary_title=f"ORACLE BROADCAST // {DATE_STAMP}",
            persona="ORACLE",
            prompt_scope="Summarize only the Predictive News page.",
        ),
        BroadcastTarget(
            markdown_path=content_dir / "Optimism.md",
            audio_filename="optimism.wav",
            summary_title=f"AURORA BROADCAST // {DATE_STAMP}",
            persona="AURORA",
            prompt_scope="Summarize only the Daily Optimism page.",
        ),
        BroadcastTarget(
            markdown_path=content_dir / "State-of-the-Grid.md",
            audio_filename="state_of_the_grid.wav",
            summary_title=f"MERIDIAN BROADCAST // {DATE_STAMP}",
            persona="MERIDIAN",
            prompt_scope="Summarize only the State of the Grid page.",
        ),
        BroadcastTarget(
            markdown_path=content_dir / "Final-Frontier.md",
            audio_filename="final_frontier.wav",
            summary_title=f"ARC BROADCAST // {DATE_STAMP}",
            persona="ARC",
            prompt_scope="Summarize only the Final Frontier page.",
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

    pipeline = None if args.dry_run else KPipeline(lang_code="a")
    generated_scripts: dict[str, str] = {}
    duration_manifest: dict[str, str] = {}

    for target in targets:
        prompt = build_prompt(target, targets, plain_text_cache)
        script_text = generate_script_via_ollama(model=args.model, prompt=prompt)
        generated_scripts[target.audio_filename] = script_text

        if args.dry_run:
            duration_label = "01:00"
        else:
            output_path = audio_dir / target.audio_filename
            duration_label = synthesize_audio(
                pipeline=pipeline,
                text=script_text,
                voice=args.voice,
                speed=args.speed,
                output_path=output_path,
            )
        duration_manifest[target.audio_filename] = duration_label
        inject_player(
            markdown_path=target.markdown_path,
            summary_title=target.summary_title,
            audio_url=target.audio_url,
            duration_label=duration_label,
            dry_run=args.dry_run,
        )

    audit_payload = {
        "generatedAt": datetime.now().isoformat(),
        "model": args.model,
        "voice": args.voice,
        "speed": args.speed,
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


def normalize_source_for_prompt(raw_text: str) -> str:
    text = raw_text
    text = re.sub(r"^---\s*\r?\n.*?^\-\-\-\s*\r?\n?", "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"`{3,}.*?`{3,}", " ", text, flags=re.DOTALL)
    text = text.replace("&mdash;", "-").replace("&nbsp;", " ")
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
        for other_target in all_targets:
            if other_target.markdown_path == target.markdown_path:
                continue
            section_text = plain_text_cache[other_target.markdown_path][:2000]
            sections.append(f"{other_target.markdown_path.stem}:\n{section_text}")
        body = "\n\n".join(sections)
    else:
        body = plain_text_cache[target.markdown_path]

    return (
        "You are writing a one-minute radio bulletin for New World Grid.\n"
        f"Desk: {target.persona}\n"
        f"Scope: {target.prompt_scope}\n"
        "Style rules:\n"
        "- Sound like a high-stakes late-1990s or early-2000s radio/news host.\n"
        "- Intense, authoritative, gritty, punchy, and cinematic.\n"
        "- Use clean spoken prose only. No bullet points, no stage directions, no markdown.\n"
        "- Do not say 'in this article' or 'on this page'. Deliver it like a live broadcast.\n"
        f"- Target {SCRIPT_WORD_TARGET} so the read lands near 60 seconds.\n"
        "- Mention concrete signals and stakes.\n"
        "- End with a hard closing line.\n\n"
        "Source material:\n"
        f"{body}\n\n"
        "Return only the final script."
    )


def generate_script_via_ollama(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.8,
            "top_p": 0.95,
            "num_predict": 260,
        },
    }
    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
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


def synthesize_audio(
    pipeline: KPipeline,
    text: str,
    voice: str,
    speed: float,
    output_path: Path,
) -> str:
    audio_chunks: list[np.ndarray] = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed):
        audio_chunks.append(np.asarray(audio, dtype=np.float32))

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


def inject_player(
    markdown_path: Path,
    summary_title: str,
    audio_url: str,
    duration_label: str,
    dry_run: bool,
) -> None:
    original = markdown_path.read_text(encoding="utf-8")
    player_block = build_player_block(summary_title, audio_url, duration_label)

    marker_pattern = re.compile(
        rf"\n?<!-- {PLAYER_MARKER}_START -->.*?<!-- {PLAYER_MARKER}_END -->\n?",
        flags=re.DOTALL,
    )
    without_existing = marker_pattern.sub("\n", original)

    if without_existing.startswith("---"):
        match = re.match(r"^---\s*\r?\n.*?\r?\n---\s*\r?\n?", without_existing, flags=re.DOTALL)
        if not match:
            raise RuntimeError(f"Could not parse frontmatter in {markdown_path}.")
        insertion_index = match.end()
        updated = without_existing[:insertion_index] + "\n" + player_block + "\n" + without_existing[insertion_index:]
    else:
        updated = player_block + "\n" + without_existing

    updated = re.sub(r"\n{3,}", "\n\n", updated)
    if not dry_run:
        markdown_path.write_text(updated, encoding="utf-8")


def build_player_block(summary_title: str, audio_url: str, duration_label: str) -> str:
    safe_title = html.escape(summary_title)
    safe_audio_url = html.escape(audio_url, quote=True)
    safe_duration = html.escape(duration_label)
    return f"""<!-- {PLAYER_MARKER}_START -->
<div class="nwg-audio-shell" data-audio-src="{safe_audio_url}">
  <div class="nwg-audio-head">
    <div class="nwg-audio-title">{safe_title}</div>
    <div class="nwg-audio-time">
      <span data-current-time>00:00</span>
      <span> / </span>
      <span data-total-time>{safe_duration}</span>
    </div>
  </div>

  <div class="nwg-audio-bar">
    <div class="nwg-audio-progress" data-progress></div>
  </div>

  <div class="nwg-audio-controls">
    <button class="nwg-audio-btn" type="button" data-role="rewind">-10s</button>
    <button class="nwg-audio-btn" type="button" data-role="play">Play</button>
    <button class="nwg-audio-btn" type="button" data-role="forward">+10s</button>
  </div>
</div>
<!-- {PLAYER_MARKER}_END -->"""


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
