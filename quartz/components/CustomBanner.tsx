import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

const CustomBanner: QuartzComponent = ({ fileData, cfg, displayClass }: QuartzComponentProps) => {
  return (
    <div class={`custom-banner ${displayClass ?? ""}`}>
      <div class="dashboard-header-wrapper">
        <div class="dashboard-header">
          <a href="/" class="banner-link-logo">
            <img src="/static/logo.png" class="custom-logo" alt="Logo" />
          </a>
          <div class="header-text">
            <a href="/" class="banner-link-text">
              <h1 class="main-title">New World Grid</h1>
              <div class="sub-title">The new reality that actually matters.</div>
            </a>
          </div>
          
          {/* Condensed Audio Player */}
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
    </div>
  )
}

CustomBanner.css = `
.custom-banner {
  margin-bottom: 1.5rem;
  position: relative;
  width: 100%;
}

.dashboard-header-wrapper {
  width: 100%;
}

/* Explicitly override any global dashboard-header styles that might hide our flex children */
.dashboard-header {
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  gap: 1.2rem !important;
  width: 100%;
}

.banner-link-logo, .banner-link-text {
  text-decoration: none !important;
  color: inherit !important;
  display: block !important;
}

.header-audio-player {
  display: flex !important;
  align-items: center !important;
  gap: 0.4rem !important;
  margin-left: auto !important;
  padding: 4px !important;
  border-radius: 30px !important;
  background: rgba(117, 255, 183, 0.08) !important;
  border: 1px solid rgba(117, 255, 183, 0.2) !important;
  z-index: 999;
}

:root[saved-theme="light"] .header-audio-player {
  background: rgba(255, 107, 0, 0.08) !important;
  border-color: rgba(255, 107, 0, 0.2) !important;
}

.header-audio-btn {
  appearance: none !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  cursor: pointer !important;
  transition: all 0.2s ease !important;
  width: 28px !important;
  height: 28px !important;
  border-radius: 50% !important;
}

:root[saved-theme="dark"] .header-audio-btn {
  color: #75ffc6 !important;
}

:root[saved-theme="light"] .header-audio-btn {
  color: #ff6b00 !important;
}

.header-audio-btn.main-play {
  width: 36px !important;
  height: 36px !important;
  background: rgba(128, 128, 128, 0.1) !important;
}

/* Hide seek buttons by default, show when playing or hover */
.header-audio-btn[data-role="rewind"],
.header-audio-btn[data-role="forward"] {
  display: none !important;
}

.header-audio-player.is-playing .header-audio-btn[data-role="rewind"],
.header-audio-player.is-playing .header-audio-btn[data-role="forward"],
.header-audio-player:hover .header-audio-btn[data-role="rewind"],
.header-audio-player:hover .header-audio-btn[data-role="forward"] {
  display: flex !important;
}

.header-audio-btn:hover {
  transform: scale(1.1) !important;
  background: rgba(128, 128, 128, 0.2) !important;
}

@media (max-width: 600px) {
  .sub-title {
    display: none !important;
  }
  .main-title {
    font-size: 1.8rem !important;
  }
  .custom-logo {
    width: 50px !important;
    height: 50px !important;
    min-width: 50px !important;
  }
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

    if (!window._nwg_audio) {
      window._nwg_audio = new Audio(src)
      window._nwg_audio.preload = "metadata"
    }
    const audio = window._nwg_audio

    const playButton = container.querySelector('[data-role="play"]')
    const rewindButton = container.querySelector('[data-role="rewind"]')
    const forwardButton = container.querySelector('[data-role="forward"]')

    const syncUi = () => {
      if (audio.paused) {
        container.classList.remove("is-playing")
        if (playButton) playButton.innerHTML = '<svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>'
      } else {
        container.classList.add("is-playing")
        if (playButton) playButton.innerHTML = '<svg data-icon="pause" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
      }
    }

    if (playButton) {
      playButton.addEventListener("click", async (e) => {
        e.preventDefault(); e.stopPropagation();
        if (audio.paused) {
          try { await audio.play(); } catch (err) { console.error(err); }
        } else {
          audio.pause();
        }
        syncUi();
      })
    }

    if (rewindButton) {
      rewindButton.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        audio.currentTime = Math.max(audio.currentTime - 10, 0);
      })
    }

    if (forwardButton) {
      forwardButton.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        const d = Number.isFinite(audio.duration) ? audio.duration : audio.currentTime + 10;
        audio.currentTime = Math.min(audio.currentTime + 10, d);
      })
    }
    
    audio.addEventListener("play", syncUi)
    audio.addEventListener("pause", syncUi)
    audio.addEventListener("timeupdate", syncUi)
    audio.addEventListener("ended", syncUi)

    syncUi()
  })
})
`

export default (() => CustomBanner) satisfies QuartzComponentConstructor
