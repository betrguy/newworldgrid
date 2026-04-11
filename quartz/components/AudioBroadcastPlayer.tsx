import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

const AudioBroadcastPlayer: QuartzComponent = ({ displayClass }: QuartzComponentProps) => {
  return (
    <div class={`nwg-audio-shell ${displayClass ?? ""}`} data-audio-src="/assets/audio/index_master_summary.wav">
      <div class="nwg-audio-head">
        <div class="nwg-audio-title">🌐 New World Grid</div>
        <div class="nwg-audio-time">
          <span data-current-time>00:00</span>
          <span> / </span>
          <span data-total-time>00:00</span>
        </div>
      </div>

      <div class="nwg-audio-bar">
        <div class="nwg-audio-progress" data-progress></div>
      </div>

      <div class="nwg-audio-controls">
        <button class="nwg-audio-btn" type="button" data-role="rewind" aria-label="Rewind 10 seconds">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg>
        </button>
        <button class="nwg-audio-btn" type="button" data-role="play" aria-label="Play">
          <svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </button>
        <button class="nwg-audio-btn" type="button" data-role="forward" aria-label="Forward 10 seconds">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
        </button>
      </div>
    </div>
  )
}

AudioBroadcastPlayer.css = `
.nwg-audio-shell {
  /* Default Dark Mode (Green) */
  --nwg-bg: linear-gradient(180deg, rgba(8, 14, 10, 0.96), rgba(13, 25, 18, 0.94));
  --nwg-border: rgba(117, 255, 183, 0.22);
  --nwg-text: #edfffa;
  --nwg-subtle: #7fac97;
  --nwg-accent: #75ffc6;
  --nwg-accent-strong: #b7ffec;
  
  position: relative;
  margin: 0.5rem 0;
  padding: 0.75rem 1rem;
  overflow: hidden;
  border: 1px solid var(--nwg-border);
  border-radius: 12px;
  background: var(--nwg-bg);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  transition: all 0.3s ease;
}

/* Light Mode Override (Orange) */
:root[saved-theme="light"] .nwg-audio-shell {
  --nwg-bg: linear-gradient(180deg, rgba(255, 248, 240, 0.98), rgba(255, 240, 225, 0.96));
  --nwg-border: rgba(255, 107, 0, 0.15);
  --nwg-text: #4a2a00;
  --nwg-subtle: #967a5a;
  --nwg-accent: #ff6b00;
  --nwg-accent-strong: #ff9e57;
  box-shadow: 0 8px 24px rgba(255, 107, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.nwg-audio-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at top right, var(--nwg-accent), transparent 40%),
    linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.04), transparent);
  opacity: 0.1;
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
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.nwg-audio-title {
  color: var(--nwg-text);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.nwg-audio-time {
  color: var(--nwg-subtle);
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.nwg-audio-bar {
  height: 4px;
  margin-bottom: 0.75rem;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
}

:root[saved-theme="dark"] .nwg-audio-bar {
  background: rgba(255, 255, 255, 0.06);
}

.nwg-audio-progress {
  width: 0%;
  height: 100%;
  background: linear-gradient(90deg, var(--nwg-accent), var(--nwg-accent-strong));
  box-shadow: 0 0 12px var(--nwg-accent);
  transition: width 120ms linear;
}

.nwg-audio-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}

.nwg-audio-btn {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  border: 1px solid var(--nwg-border);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  color: var(--nwg-text);
  cursor: pointer;
  transition: all 120ms ease;
}

.nwg-audio-btn:hover {
  transform: translateY(-1px);
  border-color: var(--nwg-accent);
  background: rgba(var(--nwg-accent), 0.1);
}

.nwg-audio-btn[data-role="play"] {
  width: 3rem;
  height: 3rem;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.1), transparent);
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

    if (!window._nwg_audio) {
      window._nwg_audio = new Audio(src)
      window._nwg_audio.preload = "metadata"
    }
    const audio = window._nwg_audio

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

    const formatTime = (seconds) => {
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

      if (audio.paused) {
        playButton.innerHTML = \`<svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>\`
      } else {
        playButton.innerHTML = \`<svg data-icon="pause" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>\`
      }
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
    
    const listeners = ["loadedmetadata", "timeupdate", "ended", "pause", "play"]
    listeners.forEach(type => audio.addEventListener(type, syncUi))

    window.addCleanup(() => {
      playButton.removeEventListener("click", onPlayPause)
      rewindButton.removeEventListener("click", onRewind)
      forwardButton.removeEventListener("click", onForward)
      listeners.forEach(type => audio.removeEventListener(type, syncUi))
    })

    syncUi()
  })
})
`

export default (() => AudioBroadcastPlayer) satisfies QuartzComponentConstructor

