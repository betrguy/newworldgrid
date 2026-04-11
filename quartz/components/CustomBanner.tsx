import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

const CustomBanner: QuartzComponent = ({ fileData, cfg, displayClass }: QuartzComponentProps) => {
  return (
    <div class={`custom-banner ${displayClass ?? ""}`}>
      <div class="dashboard-header">
        <a href="/" class="banner-link">
          <img src="/static/logo.png" class="custom-logo" alt="Logo" />
        </a>
        <div class="header-text">
          <a href="/" class="banner-link">
            <h1 class="main-title">New World Grid</h1>
            <div class="sub-title">The new reality that actually matters.</div>
          </a>
        </div>
        
        {/* Condensed Audio Player for Mobile/Top persistence */}
        <div class="header-audio-player" data-audio-src="/assets/audio/index_master_summary.wav">
          <button class="header-audio-btn" type="button" data-role="rewind" aria-label="Rewind 10s">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg>
          </button>
          <button class="header-audio-btn main-play" type="button" data-role="play" aria-label="Play">
            <svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          </button>
          <button class="header-audio-btn" type="button" data-role="forward" aria-label="Forward 10s">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
          </button>
        </div>
      </div>
    </div>
  )
}

CustomBanner.css = `
.custom-banner {
  margin-bottom: 1.5rem;
}

.dashboard-header {
  display: flex;
  align-items: center;
  gap: 1.2rem;
}

.banner-link {
  text-decoration: none;
  color: inherit;
  display: block;
}

.header-audio-player {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto; /* Push to the right end of the header row */
  padding: 4px;
  border-radius: 30px;
  background: rgba(var(--nwg-accent-rgb, 117, 255, 183), 0.05);
  border: 1px solid rgba(var(--nwg-accent-rgb, 117, 255, 183), 0.1);
}

.header-audio-btn {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--dark);
  cursor: pointer;
  transition: all 0.2s ease;
  width: 28px;
  height: 28px;
  border-radius: 50%;
}

:root[saved-theme="dark"] .header-audio-btn {
  color: #75ffc6;
}

:root[saved-theme="light"] .header-audio-btn {
  color: #ff6b00;
}

.header-audio-btn.main-play {
  width: 36px;
  height: 36px;
  background: rgba(var(--nwg-accent-rgb, 117, 255, 183), 0.1);
}

/* Hide seek buttons by default, show when playing or on hover of container */
.header-audio-btn[data-role="rewind"],
.header-audio-btn[data-role="forward"] {
  opacity: 0;
  width: 0;
  overflow: hidden;
  pointer-events: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.header-audio-player.is-playing .header-audio-btn[data-role="rewind"],
.header-audio-player.is-playing .header-audio-btn[data-role="forward"],
.header-audio-player:hover .header-audio-btn[data-role="rewind"],
.header-audio-player:hover .header-audio-btn[data-role="forward"] {
  opacity: 1;
  width: 28px;
  pointer-events: auto;
}

.header-audio-btn:hover {
  transform: scale(1.1);
  background: rgba(128, 128, 128, 0.1);
}
`

CustomBanner.afterDOMLoaded = `
document.addEventListener("nav", () => {
  const containers = document.querySelectorAll(".header-audio-player[data-audio-src]")

  containers.forEach((container) => {
    if (!(container instanceof HTMLElement) || container.dataset.bound === "true") return
    container.dataset.bound = "true"

    const src = container.dataset.audioSrc
    if (!src) return

    // Persistence Check: Reuse global audio instance
    if (!window._nwg_audio) {
      window._nwg_audio = new Audio(src)
      window._nwg_audio.preload = "metadata"
    }
    const audio = window._nwg_audio

    const playButton = container.querySelector('[data-role="play"]')
    const rewindButton = container.querySelector('[data-role="rewind"]')
    const forwardButton = container.querySelector('[data-role="forward"]')

    if (
      !(playButton instanceof HTMLButtonElement) ||
      !(rewindButton instanceof HTMLButtonElement) ||
      !(forwardButton instanceof HTMLButtonElement)
    ) {
      return
    }

    const syncUi = () => {
      // Update Play/Pause SVG
      if (audio.paused) {
        container.classList.remove("is-playing")
        playButton.innerHTML = \`<svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>\`
      } else {
        container.classList.add("is-playing")
        playButton.innerHTML = \`<svg data-icon="pause" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>\`
      }
    }

    const onPlayPause = async (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (audio.paused) {
        try {
          await audio.play()
        } catch (error) {
          console.error("Header audio playback failed", error)
        }
      } else {
        audio.pause()
      }
      syncUi()
    }

    playButton.addEventListener("click", onPlayPause)
    rewindButton.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      audio.currentTime = Math.max(audio.currentTime - 10, 0)
    })
    forwardButton.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      const duration = Number.isFinite(audio.duration) ? audio.duration : audio.currentTime + 10
      audio.currentTime = Math.min(audio.currentTime + 10, duration)
    })
    
    const listeners = ["loadedmetadata", "timeupdate", "ended", "pause", "play"]
    listeners.forEach(type => audio.addEventListener(type, syncUi))

    window.addCleanup(() => {
      listeners.forEach(type => audio.removeEventListener(type, syncUi))
    })

    syncUi()
  })
})
`

export default (() => CustomBanner) satisfies QuartzComponentConstructor
