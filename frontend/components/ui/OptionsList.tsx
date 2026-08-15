"use client";

import { useEffect, useRef, useState } from "react";
import { Box, Text } from "@/components/ui/primitives";
import { optionLabel } from "@/lib/content/options";
import styles from "./OptionsList.module.css";

export type OptionItem = {
  key: string;
  text: string;
};

export function OptionsList(props: {
  options: OptionItem[];
  itemKeyPrefix: string;
  renderOptionText: (opt: OptionItem, forceWrap: boolean) => React.ReactElement;
}) {
  const { options, itemKeyPrefix, renderOptionText } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [optionsColumns, setOptionsColumns] = useState<1 | 2 | 4>(4);

  useEffect(() => {
    if (options.length === 0) return;

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

  const visibleOptionsColumns = options.length === 0 ? 4 : optionsColumns;
  const forceWrap = visibleOptionsColumns === 1;

  return (
    <Box
      ref={containerRef}
      className={styles.optionsGrid}
      data-columns={visibleOptionsColumns}
    >
      {options.map((opt, index) => (
        <Box
          key={`${itemKeyPrefix}-${opt.key}`}
          data-option-item="true"
          className={styles.optionItem}
        >
          <Text weight="bold">{optionLabel(index)}.</Text>
          <Box
            data-option-text="true"
            className={forceWrap ? styles.optionTextWrap : styles.optionText}
          >
            {renderOptionText(opt, forceWrap)}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
