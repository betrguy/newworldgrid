import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * Quartz 4 Configuration
 *
 * See https://quartz.jzhao.xyz/configuration for more information.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "New World Grid",
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: false, // We disabled this earlier, keep it false
    analytics: {
      provider: "plausible",
    },
    locale: "en-US",
    
    // --- SEO CRITICAL UPDATES ---
    baseUrl: "thenewworldgrid.com", // NO "https://" here, just the domain
    ignorePatterns: ["private", "templates", ".obsidian"],
    defaultDateType: "modified",
    
    // The "Meta Description" for Google
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        // We add Libre Baskerville here so it downloads
        header: "Libre Baskerville", 
        body: "Source Sans Pro",
        code: "JetBrains Mono",
      },
      colors: {
        lightMode: {
          light: "#faf8f8",
          lightgray: "#e5e5e5",
          gray: "#b8b8b8",
          darkgray: "#4e4e4e",
          dark: "#2b2b2b",
          secondary: "#284b63",
          tertiary: "#84a59d",
          highlight: "rgba(143, 159, 169, 0.15)",
          textHighlight: "#fff23688",
        },
        darkMode: {
          light: "#0a0a0a",        // Pitch black background
          lightgray: "#393639",    // Subtle borders
          gray: "#646464",         // Muted text
          darkgray: "#d4d4d4",     // Main text (readable grey-white)
          dark: "#ffffff",         // Headings (stark white)
          secondary: "#00ff41",    // THE TERMINAL GREEN (Links/Accents)
          tertiary: "#ff3333",     // Alert Red (for hover states)
          highlight: "rgba(0, 255, 65, 0.15)", // Green highlight
          textHighlight: "#b3a06d88",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(), 
      Plugin.NotFoundPage(),
      Plugin.CustomOgImages(),
    ],
  },
}

export default config