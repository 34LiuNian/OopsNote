"use client";

import { useEffect, useRef, useState } from "react";
import { Box, Text } from "@primer/react";

export type OptionItem = {
  key: string;
  text: string;
  latex_blocks?: string[];
};

export function OptionsList(props: {
  options: OptionItem[];
  itemKeyPrefix: string;
  renderOptionText: (opt: OptionItem, forceWrap: boolean) => JSX.Element;
}) {
  const { options, itemKeyPrefix, renderOptionText } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [optionsColumns, setOptionsColumns] = useState<1 | 2 | 4>(4);

  useEffect(() => {
    if (options.length === 0) {
      setOptionsColumns(4);
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    let rafId = 0;
    const checkOverflow = () => {
      const host = containerRef.current;
      if (!host) return;

      host.setAttribute("data-measuring", "true");
      void host.offsetWidth;

      const items = Array.from(host.querySelectorAll<HTMLElement>("[data-option-item='true']"));
      const maxItemWidth = items.reduce((max, el) => Math.max(max, el.scrollWidth), 0);
      const computed = window.getComputedStyle(host);
      const gap = parseFloat(computed.columnGap || computed.gap || "0") || 0;
      const containerWidth = host.clientWidth;

      const canFit = (cols: 1 | 2 | 4) => {
        if (cols === 1) return true;
        const totalGap = gap * (cols - 1);
        const colWidth = (containerWidth - totalGap) / cols;
        return maxItemWidth <= colWidth;
      };

      const nextCols: 1 | 2 | 4 = canFit(4) ? 4 : canFit(2) ? 2 : 1;
      setOptionsColumns((prev) => (prev === nextCols ? prev : nextCols));

      host.removeAttribute("data-measuring");
    };

    const scheduleCheck = () => {
      if (rafId) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(checkOverflow);
    };

    scheduleCheck();
    const ro = new ResizeObserver(scheduleCheck);
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (rafId) window.cancelAnimationFrame(rafId);
    };
  }, [options]);

  const forceWrap = optionsColumns === 1;

  return (
    <Box
      ref={containerRef}
      sx={{
        mt: 2,
        display: "grid",
        gridTemplateColumns: `repeat(${optionsColumns}, minmax(0, 1fr))`,
        gap: 2,
        "&[data-measuring='true'] [data-option-text='true']": {
          whiteSpace: "nowrap",
          overflowWrap: "normal",
        },
        "&[data-measuring='true'] [data-option-item='true']": {
          width: "max-content",
          justifySelf: "start",
        },
      }}
    >
      {options.map((opt) => (
        <Box
          key={`${itemKeyPrefix}-${opt.key}`}
          data-option-item="true"
          sx={{
            display: "inline-flex",
            alignItems: "baseline",
            gap: 1,
            justifySelf: "start",
            maxWidth: "100%",
          }}
        >
          <Text sx={{ fontWeight: "bold" }}>{opt.key}.</Text>
          <Box
            data-option-text="true"
            sx={{
              whiteSpace: forceWrap ? "normal" : "nowrap",
              overflowWrap: forceWrap ? "anywhere" : "normal",
              "& p": { display: "inline", margin: 0 },
            }}
          >
            {renderOptionText(opt, forceWrap)}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
