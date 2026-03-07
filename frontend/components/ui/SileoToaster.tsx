"use client";

import { Toaster } from "sileo";

export function SileoToaster() {
  return <Toaster position="top-center" options={{
    fill: "#000000",
    roundness: 8,
    styles: {
      title: "!text-white",
      description: "!text-white/75",
      badge: "!bg-white/20",
      button: "!bg-white/10",
    },
  }} />;
}
