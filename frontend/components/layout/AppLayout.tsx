"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Box, Text } from "@/components/ui/primitives";
import {
  SidebarCollapseIcon,
  SidebarExpandIcon,
} from "@/components/ui/icons";
import { Sidebar } from "./Sidebar";
import { MobileTabBar } from "./MobileTabBar";
import { BackendStatus } from "../ui/BackendStatus";
import { AccountMenu } from "./AccountMenu";
import {
  SecondarySidebarProvider,
  type SecondarySidebarView,
} from "./SecondarySidebarContext";

type DesktopSidebarView = "primary-expanded" | "primary-collapsed" | "context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLibrary = pathname.startsWith("/library");
  const defaultDesktopSidebarView: DesktopSidebarView = isLibrary
    ? "context"
    : "primary-expanded";
  const [desktopSidebarState, setDesktopSidebarState] = useState<{
    pathname: string;
    view: DesktopSidebarView;
  }>(() => ({ pathname, view: defaultDesktopSidebarView }));
  const desktopSidebarView = desktopSidebarState.pathname === pathname
    ? desktopSidebarState.view
    : defaultDesktopSidebarView;
  const sidebarCollapsed = desktopSidebarView !== "primary-expanded";
  const secondaryView: SecondarySidebarView = isLibrary && desktopSidebarView === "context"
    ? "context"
    : "closed";
  const [secondaryTarget, setSecondaryTarget] = useState<HTMLDivElement | null>(null);
  const [mobileSecondaryState, setMobileSecondaryState] = useState({
    pathname,
    open: false,
  });
  const mobileSecondaryOpen = mobileSecondaryState.pathname === pathname
    ? mobileSecondaryState.open
    : false;
  const isMobileViewport = typeof window !== "undefined"
    && window.matchMedia("(max-width: 543px)").matches;
  const contextSidebarOpen = isMobileViewport
    ? mobileSecondaryOpen
    : secondaryView === "context";
  const contentSurfaceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentSurfaceRef.current) contentSurfaceRef.current.scrollTop = 0;
  }, [pathname]);

  const openContextSidebar = useCallback(() => {
    setDesktopSidebarState({ pathname, view: "context" });
    setMobileSecondaryState({ pathname, open: true });
  }, [pathname]);

  const closeSecondarySidebar = useCallback(() => {
    setDesktopSidebarState({ pathname, view: "primary-expanded" });
    setMobileSecondaryState({ pathname, open: false });
  }, [pathname]);

  const toggleContextSidebar = useCallback(() => {
    if (isMobileViewport ? mobileSecondaryOpen : secondaryView === "context") {
      closeSecondarySidebar();
      return;
    }
    openContextSidebar();
  }, [closeSecondarySidebar, isMobileViewport, mobileSecondaryOpen, openContextSidebar, secondaryView]);

  const handleNavigation = useCallback((href: string) => {
    setDesktopSidebarState({
      pathname: href,
      view: href.startsWith("/library") ? "context" : "primary-expanded",
    });
    setMobileSecondaryState({ pathname: href, open: false });
  }, []);

  const togglePrimarySidebar = useCallback(() => {
    setDesktopSidebarState({
      pathname,
      view: isLibrary
        ? desktopSidebarView === "context" ? "primary-expanded" : "context"
        : desktopSidebarView === "primary-collapsed" ? "primary-expanded" : "primary-collapsed",
    });
    setMobileSecondaryState({ pathname, open: false });
  }, [desktopSidebarView, isLibrary, pathname]);

  const toggleLabel = isLibrary
    ? desktopSidebarView === "context" ? "展开主导航" : "打开题库筛选"
    : sidebarCollapsed ? "展开侧栏" : "收起侧栏";
  const ToggleIcon = sidebarCollapsed ? SidebarExpandIcon : SidebarCollapseIcon;

  return (
    <SecondarySidebarProvider
      value={{
        target: secondaryTarget,
        view: secondaryView,
        contextSidebarOpen,
        openContextSidebar,
        toggleContextSidebar,
        closeSecondarySidebar,
      }}
    >
      <Box className={`oops-app-shell${sidebarCollapsed ? " is-sidebar-collapsed" : ""}${secondaryView === "context" ? " is-secondary-open" : " is-secondary-closed"}`}>
        <Box as="header" className="oops-titlebar">
          <button
            className="oops-titlebar__brand-toggle"
            type="button"
            onClick={togglePrimarySidebar}
            aria-label={toggleLabel}
            aria-controls="oops-primary-sidebar"
            aria-expanded={!sidebarCollapsed}
            title={toggleLabel}
          >
            <span className="oops-titlebar__brand-icon" aria-hidden="true">
              <span className="oops-titlebar__brand-mark" />
              <span className="oops-titlebar__brand-action">
                <ToggleIcon size={28} strokeWidth={1.7} />
              </span>
            </span>
            <Text>OopsNote</Text>
          </button>
          <Text className="oops-titlebar__mobile-brand">OopsNote</Text>
          <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
            <BackendStatus />
            <AccountMenu />
          </Box>
        </Box>

        <Box className="oops-app-body">
          <Sidebar collapsed={sidebarCollapsed} onNavigate={handleNavigation} />
          {isLibrary ? (
            <>
              <aside
                id="oops-secondary-sidebar"
                className={`oops-secondary-sidebar${secondaryView === "closed" ? " is-closed" : ""}${mobileSecondaryOpen ? " is-mobile-open" : ""}`}
                aria-label="题库筛选"
              >
                <div
                  ref={setSecondaryTarget}
                  className={`oops-secondary-sidebar__view oops-secondary-sidebar__view--context${secondaryView === "context" ? " is-active" : ""}`}
                />
              </aside>
              <button
                type="button"
                className={`oops-secondary-sidebar__backdrop${mobileSecondaryOpen ? " is-visible" : ""}`}
                aria-label="关闭题库筛选"
                onClick={closeSecondarySidebar}
              />
            </>
          ) : null}
          <Box ref={contentSurfaceRef} className="oops-content-surface">
            <Box as="main" sx={{ px: [3, 4, 5], py: [3, 4], flex: 1, width: "100%", pb: ["80px", 4] }}>
              <div key={pathname} className="oops-page-enter">
                {children}
              </div>
            </Box>
          </Box>
        </Box>
        <MobileTabBar />
      </Box>
    </SecondarySidebarProvider>
  );
}
