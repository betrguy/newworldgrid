import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

// components shared across all pages
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [],
  footer: Component.Footer({
    links: {
      GitHub: "https://github.com/jackyzha0/quartz",
      "Discord Community": "https://discord.gg/cRFFHYye7t",
    },
  }),
}

// components for pages that display a single page (e.g. a single note)
export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.CustomBanner(),
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.TagList(),
  ],
  left: [
    Component.MobileOnly(Component.Spacer()),
    Component.Search(),
    Component.Darkmode(),
    Component.Explorer({
      title: "Signals",
      folderDefaultState: "collapsed",
      folderClickBehavior: "link",
      useSavedState: false,
      filterFn: (node) => {
        if (node.slugSegment === "tags") return false
        if (/^\d{4}-\d{2}-\d{2}/.test(node.slugSegment)) return false
        return true
      },
      mapFn: (node) => {
        const names: Record<string, string> = {
          "The-Surge": "The Surge",
          "National-Shadow-GDP": "Nat. Shadow GDP",
          "Predictive-News": "Predictive News",
        }
        if (names[node.displayName]) {
          node.displayName = names[node.displayName]
        }
      },
      sortFn: (a, b) => {
        const order = ["The Surge", "Predictive News", "Nat. Shadow GDP"]
        const ai = order.indexOf(a.displayName)
        const bi = order.indexOf(b.displayName)
        if (ai !== -1 && bi !== -1) return ai - bi
        if (ai !== -1) return -1
        if (bi !== -1) return 1
        return a.displayName.localeCompare(b.displayName)
      },
    }),
  ],
  right: [
    Component.DesktopOnly(Component.TableOfContents()),
  ],
}

// components for pages that display lists of pages (e.g. tags or folders)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.CustomBanner(), Component.Breadcrumbs(),], // No ContentMeta = No Date
  left: [
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
      ],
    }),
    Component.Explorer({
      title: "Signals",
      folderDefaultState: "collapsed",
      folderClickBehavior: "link",
      useSavedState: false,
      filterFn: (node) => {
        if (node.slugSegment === "tags") return false
        if (/^\d{4}-\d{2}-\d{2}/.test(node.slugSegment)) return false
        return true
      },
      mapFn: (node) => {
        const names: Record<string, string> = {
          "The-Surge": "The Surge",
          "National-Shadow-GDP": "Nat. Shadow GDP",
          "Predictive-News": "Predictive News",
        }
        if (names[node.displayName]) {
          node.displayName = names[node.displayName]
        }
      },
      sortFn: (a, b) => {
        const order = ["The Surge", "Predictive News", "Nat. Shadow GDP"]
        const ai = order.indexOf(a.displayName)
        const bi = order.indexOf(b.displayName)
        if (ai !== -1 && bi !== -1) return ai - bi
        if (ai !== -1) return -1
        if (bi !== -1) return 1
        return a.displayName.localeCompare(b.displayName)
      },
    }),
  ],
  right: [],
}