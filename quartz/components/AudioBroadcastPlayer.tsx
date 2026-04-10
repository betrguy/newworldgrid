import { QuartzComponent, QuartzComponentConstructor } from "./types"

const AudioBroadcastPlayer: QuartzComponent = () => null

AudioBroadcastPlayer.css = `
.nwg-audio-shell {
  --nwg-bg: linear-gradient(180deg, rgba(8, 10, 14, 0.96), rgba(13, 18, 25, 0.94));
  --nwg-border: rgba(117, 198, 255, 0.22);
  --nwg-text: #edf6ff;
  --nwg-subtle: #7f97ac;
  --nwg-accent: #75c6ff;
  --nwg-accent-strong: #b7ecff;
  position: relative;
  margin: 1.1rem 0 1.5rem;
  padding: 1rem;
  overflow: hidden;
  border: 1px solid var(--nwg-border);
  border-radius: 18px;
  background: var(--nwg-bg);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.nwg-audio-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at top right, rgba(117, 198, 255, 0.14), transparent 34%),
    linear-gradient(90deg, transparent, rgba(117, 198, 255, 0.08), transparent);
}

.nwg-audio-head,
.nwg-audio-bar,
.nwg-audio-controls {
  position: relative;
  z-index: 1;
}

.nwg-audio-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.9rem;
}

.nwg-audio-title {
  color: var(--nwg-text);
  font-size: 0.86rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  line-height: 1.4;
  text-transform: uppercase;
}

.nwg-audio-time {
  color: var(--nwg-subtle);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.nwg-audio-bar {
  height: 5px;
  margin-bottom: 0.95rem;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.nwg-audio-progress {
  width: 0%;
  height: 100%;
  background: linear-gradient(90deg, var(--nwg-accent), var(--nwg-accent-strong));
  box-shadow: 0 0 18px rgba(117, 198, 255, 0.45);
  transition: width 120ms linear;
}

.nwg-audio-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.nwg-audio-btn {
  appearance: none;
  min-width: 3rem;
  height: 3rem;
  padding: 0 1rem;
  border: 1px solid rgba(117, 198, 255, 0.26);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--nwg-text);
  cursor: pointer;
  font-size: 0.82rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}

.nwg-audio-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(183, 236, 255, 0.65);
  background: rgba(117, 198, 255, 0.12);
}

.nwg-audio-btn[data-role="play"] {
  min-width: 5.5rem;
  font-weight: 700;
  background: linear-gradient(180deg, rgba(117, 198, 255, 0.22), rgba(117, 198, 255, 0.08));
}

@media (max-width: 720px) {
  .nwg-audio-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .nwg-audio-controls {
    width: 100%;
  }

  .nwg-audio-btn[data-role="play"] {
    flex: 1 1 100%;
  }
}
`

AudioBroadcastPlayer.afterDOMLoaded = `
document.addEventListener("nav", () => {
  const roots = document.querySelectorAll(".nwg-audio-shell[data-audio-src]")

  roots.forEach((root) => {
    if (!(root instanceof HTMLElement) || root.dataset.bound === "true") return
    root.dataset.bound = "true"

    const src = root.dataset.audioSrc
    if (!src) return

    const audio = new Audio(src)
    audio.preload = "metadata"

    const currentNode = root.querySelector("[data-current-time]")
    const totalNode = root.querySelector("[data-total-time]")
    const progressNode = root.querySelector("[data-progress]")
    const playButton = root.querySelector('[data-role="play"]')
    const rewindButton = root.querySelector('[data-role="rewind"]')
    const forwardButton = root.querySelector('[data-role="forward"]')

    if (
      !(currentNode instanceof HTMLElement) ||
      !(totalNode instanceof HTMLElement) ||
      !(progressNode instanceof HTMLElement) ||
      !(playButton instanceof HTMLButtonElement) ||
      !(rewindButton instanceof HTMLButtonElement) ||
      !(forwardButton instanceof HTMLButtonElement)
    ) {
      return
    }

    const formatTime = (seconds: number) => {
      if (!Number.isFinite(seconds) || seconds < 0) return "00:00"
      const whole = Math.floor(seconds)
      const mins = String(Math.floor(whole / 60)).padStart(2, "0")
      const secs = String(whole % 60).padStart(2, "0")
      return mins + ":" + secs
    }

    const syncUi = () => {
      currentNode.textContent = formatTime(audio.currentTime)
      const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0

      if (duration > 0) {
        totalNode.textContent = formatTime(duration)
        progressNode.setAttribute("style", "width:" + String((audio.currentTime / duration) * 100) + "%")
      } else {
        progressNode.setAttribute("style", "width:0%")
      }

      playButton.textContent = audio.paused ? "Play" : "Pause"
    }

    const onPlayPause = async () => {
      if (audio.paused) {
        try {
          await audio.play()
        } catch (error) {
          console.error("Audio playback failed", error)
        }
      } else {
        audio.pause()
      }
      syncUi()
    }

    const onRewind = () => {
      audio.currentTime = Math.max(audio.currentTime - 10, 0)
      syncUi()
    }

    const onForward = () => {
      const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : audio.currentTime + 10
      audio.currentTime = Math.min(audio.currentTime + 10, duration)
      syncUi()
    }

    playButton.addEventListener("click", onPlayPause)
    rewindButton.addEventListener("click", onRewind)
    forwardButton.addEventListener("click", onForward)
    audio.addEventListener("loadedmetadata", syncUi)
    audio.addEventListener("timeupdate", syncUi)
    audio.addEventListener("ended", syncUi)
    audio.addEventListener("pause", syncUi)
    audio.addEventListener("play", syncUi)

    window.addCleanup(() => {
      playButton.removeEventListener("click", onPlayPause)
      rewindButton.removeEventListener("click", onRewind)
      forwardButton.removeEventListener("click", onForward)
      audio.pause()
      audio.src = ""
    })

    syncUi()
  })
})
`

export default (() => AudioBroadcastPlayer) satisfies QuartzComponentConstructor
