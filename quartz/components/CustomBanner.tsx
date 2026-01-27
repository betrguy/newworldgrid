import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

const CustomBanner: QuartzComponent = ({ fileData, cfg, displayClass }: QuartzComponentProps) => {
  return (
    <div class={`custom-banner ${displayClass ?? ""}`}>
      <a href="/" class="banner-link">
        <div class="dashboard-header">
          <img src="/static/logo.png" class="custom-logo" alt="Logo" />
          <div class="header-text">
            <h1 class="main-title">New World Grid</h1>
            <div class="sub-title">The new reality that actually matters.</div>
          </div>
        </div>
      </a>
    </div>
  )
}

// We embed the link styling here to ensure it doesn't look like a blue hyperlink
CustomBanner.css = `
.banner-link {
  text-decoration: none;
  color: inherit;
  display: block;
  cursor: pointer;
}

/* Ensure the banner sits nicely above breadcrumbs */
.custom-banner {
  margin-bottom: 1.5rem; 
}
`

export default (() => CustomBanner) satisfies QuartzComponentConstructor