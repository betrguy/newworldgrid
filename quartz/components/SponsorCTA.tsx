import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

interface Options {
  title?: string
  description?: string
  ctaText?: string
  targetPage?: string
  showOnPages?: "all" | "briefings"
}

const defaults: Options = {
  title: "Sponsor This Briefing",
  description: "Reach decision-makers tracking energy, geopolitics, and market signals.",
  ctaText: "View Sponsorship Options",
  targetPage: "/sponsor",
  showOnPages: "briefings",
}

export default ((userOpts?: Options) => {
  const opts = { ...defaults, ...userOpts }

  const SponsorCTA: QuartzComponent = ({ displayClass, fileData }: QuartzComponentProps) => {
    if (opts.showOnPages === "briefings") {
      const slug = fileData.slug ?? ""
      const isBriefing =
        slug.includes("The-Surge") ||
        slug.includes("Predictive-News") ||
        slug.includes("National-Shadow-GDP") ||
        slug.includes("The-Big-Read")
      if (!isBriefing) return null
    }

    return (
      <aside class={`sponsor-cta ${displayClass ?? ""}`}>
        <div class="sponsor-container">
          <div class="sponsor-header">
            <span class="sponsor-badge">Sponsor</span>
            <h4 class="sponsor-title">{opts.title}</h4>
          </div>
          <p class="sponsor-description">{opts.description}</p>
          <a href={opts.targetPage} class="sponsor-button">
            {opts.ctaText} <span class="sponsor-arrow">&rarr;</span>
          </a>
        </div>
      </aside>
    )
  }

  SponsorCTA.css = `
.sponsor-cta {
  width: 100%;
  margin: 2.5rem auto;
  padding: 1.5rem;
  background: rgba(0, 255, 65, 0.05);
  border: 1px solid var(--gray);
  border-top: 3px solid var(--secondary);
}

.sponsor-container {
  max-width: 600px;
  margin: 0 auto;
}

.sponsor-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.sponsor-badge {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--light);
  background: var(--secondary);
  padding: 0.25rem 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.sponsor-title {
  font-family: "Libre Baskerville", serif !important;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--dark);
  margin: 0;
  letter-spacing: -0.01em;
}

.sponsor-description {
  font-family: "Source Sans Pro", sans-serif;
  font-size: 0.9rem;
  color: var(--darkgray);
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.sponsor-button {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.7rem 1.2rem;
  background: transparent;
  color: var(--secondary);
  border: 1px solid var(--secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  text-decoration: none;
  letter-spacing: 0.05em;
  transition: all 0.2s ease;
}

.sponsor-button:hover {
  background: var(--secondary);
  color: var(--light);
}

.sponsor-arrow {
  font-size: 1.2rem;
  transition: transform 0.2s ease;
}

.sponsor-button:hover .sponsor-arrow {
  transform: translateX(4px);
}

@media (max-width: 600px) {
  .sponsor-cta {
    padding: 1.25rem;
    margin: 2rem auto;
  }

  .sponsor-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .sponsor-button {
    width: 100%;
    justify-content: center;
    min-height: 48px;
  }

  .sponsor-title {
    font-size: 1rem;
  }
}
`

  return SponsorCTA
}) satisfies QuartzComponentConstructor
