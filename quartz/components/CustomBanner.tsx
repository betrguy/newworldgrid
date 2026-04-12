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
          
          {/* NWG Header Audio Player - V4 Stationary Anchor */}
          <div class="nwg-header-player" data-audio-src="/assets/audio/index_master_summary.wav">
            {/* We use row-reverse so Play stays on the right and others expand left */}
            <button class="nwg-header-btn main-play" type="button" data-role="play" aria-label="Play">
              <svg data-icon="play" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </button>
            <button class="nwg-header-btn" type="button" data-role="forward" aria-label="Forward 10s">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
            </button>
            <button class="nwg-header-btn" type="button" data-role="rewind" aria-label="Rewind 10s">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg>
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

.dashboard-header {
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  gap: 1.2rem !important;
  width: 100%;
}

.nwg-header-player {
  display: flex !important;
  flex-direction: row-reverse !important; /* Play button is the rightmost anchor */
  align-items: center !important;
  gap: 0.4rem !important;
  margin-left: auto !important;
  padding: 4px !important;
  border-radius: 30px !important;
  background: rgba(117, 255, 183, 0.08) !important;
  border: 1px solid rgba(117, 255, 183, 0.2) !important;
  z-index: 9999 !important;
  transition: all 0.3s ease !important;
}

:root[saved-theme="light"] .nwg-header-player {
  background: rgba(255, 107, 0, 0.08) !important;
  border-color: rgba(255, 107, 0, 0.2) !important;
}

.nwg-header-btn {
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
  flex-shrink: 0 !important;
}

:root[saved-theme="dark"] .nwg-header-btn {
  color: #75ffc6 !important;
}

:root[saved-theme="light"] .nwg-header-btn {
  color: #ff6b00 !important;
}

.nwg-header-btn.main-play {
  width: 36px !important;
  height: 36px !important;
  background: rgba(128, 128, 128, 0.1) !important;
}

/* Hidden buttons have 0 width and opacity to avoid shifting the Play button anchor */
.nwg-header-btn[data-role="rewind"],
.nwg-header-btn[data-role="forward"] {
  width: 0 !important;
  opacity: 0 !important;
  overflow: hidden !important;
  pointer-events: none !important;
  margin: 0 !important;
}

.nwg-header-player.is-playing .nwg-header-btn[data-role="rewind"],
.nwg-header-player.is-playing .nwg-header-btn[data-role="forward"],
.nwg-header-player:hover .nwg-header-btn[data-role="rewind"],
.nwg-header-player:hover .nwg-header-btn[data-role="forward"] {
  width: 28px !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  margin: 0 2px !important;
}

@media (max-width: 600px) {
  .sub-title { display: none !important; }
  .main-title { font-size: 1.6rem !important; }
  .dashboard-header { gap: 0.6rem !important; }
}
`

CustomBanner.afterDOMLoaded = `
document.addEventListener("nav", () => {
  const containers = document.querySelectorAll(".nwg-header-player[data-audio-src]")

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
          try { 
            // Immediate UI feedback before the promise resolves
            container.classList.add("is-playing");
            await audio.play(); 
          } catch (err) { 
            console.error(err);
            container.classList.remove("is-playing");
          }
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
    
    // Use named functions to avoid duplicate listeners on nav
    const boundSync = () => syncUi();
    audio.addEventListener("play", boundSync);
    audio.addEventListener("pause", boundSync);
    audio.addEventListener("timeupdate", boundSync);
    audio.addEventListener("ended", boundSync);

    syncUi();
  })
})
`

export default (() => CustomBanner) satisfies QuartzComponentConstructor
