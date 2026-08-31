"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Box, Button, GeometryButton, Text } from "@/components/ui/primitives";
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
import sxStyles from "./AppLayout.sx.module.css";

type DesktopSidebarState = {
  pathname: string;
  primaryCollapsed: boolean;
  secondaryOpen: boolean;
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLibrary = pathname.startsWith("/library");
  const isChannels = pathname.startsWith("/settings/channels");
  const isPaperCompose = pathname === "/papers/new";
  const isCatalogSidebar = isLibrary || isChannels;
  const hasSecondarySidebar = isCatalogSidebar || isPaperCompose;
  const defaultDesktopSidebarState: DesktopSidebarState = {
    pathname,
    primaryCollapsed: isLibrary,
    secondaryOpen: hasSecondarySidebar,
  };
  const [desktopSidebarState, setDesktopSidebarState] = useState<DesktopSidebarState>(defaultDesktopSidebarState);
  const activeDesktopSidebarState = desktopSidebarState.pathname === pathname
    ? desktopSidebarState
    : defaultDesktopSidebarState;
  const sidebarCollapsed = activeDesktopSidebarState.primaryCollapsed;
  const secondaryView: SecondarySidebarView = hasSecondarySidebar && activeDesktopSidebarState.secondaryOpen
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
    setDesktopSidebarState({
      ...activeDesktopSidebarState,
      pathname,
      secondaryOpen: true,
    });
    setMobileSecondaryState({ pathname, open: true });
  }, [activeDesktopSidebarState, pathname]);

  const closeSecondarySidebar = useCallback(() => {
    setDesktopSidebarState({
      ...activeDesktopSidebarState,
      pathname,
      secondaryOpen: false,
    });
    setMobileSecondaryState({ pathname, open: false });
  }, [activeDesktopSidebarState, pathname]);

  const toggleContextSidebar = useCallback(() => {
    if (isMobileViewport ? mobileSecondaryOpen : secondaryView === "context") {
      closeSecondarySidebar();
      return;
    }
    openContextSidebar();
  }, [closeSecondarySidebar, isMobileViewport, mobileSecondaryOpen, openContextSidebar, secondaryView]);

  const handleNavigation = useCallback((href: string) => {
    const nextIsLibrary = href.startsWith("/library");
    const nextIsPaperCompose = href === "/papers/new";
    const nextHasSecondarySidebar = nextIsLibrary || href.startsWith("/settings/channels") || nextIsPaperCompose;
    setDesktopSidebarState({
      pathname: href,
      primaryCollapsed: nextIsLibrary,
      secondaryOpen: nextHasSecondarySidebar,
    });
    setMobileSecondaryState({ pathname: href, open: false });
  }, []);

  const togglePrimarySidebar = useCallback(() => {
    setDesktopSidebarState({
      ...activeDesktopSidebarState,
      pathname,
      primaryCollapsed: !activeDesktopSidebarState.primaryCollapsed,
    });
  }, [activeDesktopSidebarState, pathname]);

  const secondaryLabel = isLibrary ? "题库筛选" : isChannels ? "AI 渠道" : "组卷筛选";
  const toggleLabel = sidebarCollapsed ? "展开侧栏" : "收起侧栏";
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
      <Box className={`oops-app-shell${sidebarCollapsed ? " is-sidebar-collapsed" : ""}${secondaryView === "context" ? " is-secondary-open" : " is-secondary-closed"}${isCatalogSidebar ? " is-secondary-catalog" : ""}${isPaperCompose ? " is-secondary-paper-compose" : ""}`}>
        <Box as="header" className="oops-titlebar">
          <Button
            variant="default"
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
          </Button>
          <Text className="oops-titlebar__mobile-brand">OopsNote</Text>
          <Box className="oops-titlebar__actions">
            <Box className={sxStyles.sx1}>
            <BackendStatus />
            <AccountMenu />
            </Box>
          </Box>
        </Box>

        <Box className="oops-app-body">
          <Sidebar collapsed={sidebarCollapsed} onNavigate={handleNavigation} />
          {hasSecondarySidebar ? (
            <>
              <aside
                id="oops-secondary-sidebar"
                className={`oops-secondary-sidebar${secondaryView === "closed" ? " is-closed" : ""}${mobileSecondaryOpen ? " is-mobile-open" : ""}`}
                aria-label={secondaryLabel}
              >
                <div
                  ref={setSecondaryTarget}
                  className={`oops-secondary-sidebar__view oops-secondary-sidebar__view--context${secondaryView === "context" ? " is-active" : ""}`}
                />
              </aside>
              <GeometryButton
                type="button"
                className={`oops-secondary-sidebar__backdrop${mobileSecondaryOpen ? " is-visible" : ""}`}
                aria-label={`关闭${secondaryLabel}`}
                onClick={closeSecondarySidebar}
              />
            </>
          ) : null}
          <Box ref={contentSurfaceRef} className="oops-content-surface">
            <Box as="main" className={sxStyles.sx2}>
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
