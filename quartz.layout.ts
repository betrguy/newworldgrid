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
    // ADDED: This ensures the sidebar tree appears on articles too
    Component.Explorer({
      title: "New World Grid",
      folderDefaultState: "open",
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
      title: "New World Grid", // Custom Title
      folderDefaultState: "open", // Keeps the tree open so users see content
    }),
  ],
  right: [],
}