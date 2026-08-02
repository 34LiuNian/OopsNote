"use client";

import { createContext, useContext } from "react";

export type SecondarySidebarView = "closed" | "context";

type SecondarySidebarContextValue = {
  target: HTMLDivElement | null;
  view: SecondarySidebarView;
  contextSidebarOpen: boolean;
  openContextSidebar: () => void;
  toggleContextSidebar: () => void;
  closeSecondarySidebar: () => void;
};

const SecondarySidebarContext = createContext<SecondarySidebarContextValue>({
  target: null,
  view: "closed",
  contextSidebarOpen: false,
  openContextSidebar: () => undefined,
  toggleContextSidebar: () => undefined,
  closeSecondarySidebar: () => undefined,
});

export function SecondarySidebarProvider({
  children,
  value,
}: {
  children: React.ReactNode;
  value: SecondarySidebarContextValue;
}) {
  return (
    <SecondarySidebarContext.Provider value={value}>
      {children}
    </SecondarySidebarContext.Provider>
  );
}

export function useSecondarySidebar() {
  return useContext(SecondarySidebarContext);
}
