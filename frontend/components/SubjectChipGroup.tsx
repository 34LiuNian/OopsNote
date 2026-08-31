"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { Box } from "@/components/ui/primitives";
import styles from "./SubjectChipGroup.module.css";

function SubjectChip({
  item,
  selected,
  onSelect,
}: {
  item: { value: string; label: string };
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <Box
      as="button"
      type="button"
      className={styles.chip}
      data-selected={selected ? "true" : "false"}
      role="radio"
      aria-checked={selected}
      title={item.label}
      onClick={onSelect}
    >
      {item.label}
    </Box>
  );
}

export function SubjectChipGroup({
  value,
  onChange,
  options,
  includeAll = false,
  allLabel = "全部",
  layout = "overlay",
  className,
  "aria-label": ariaLabel = "学科",
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  includeAll?: boolean;
  allLabel?: string;
  layout?: "overlay" | "spread";
  className?: string;
  "aria-label"?: string;
}) {
  const items = includeAll ? [{ value: "", label: allLabel }, ...options] : options;
  const selectedItem = items.find((item) => item.value === value);
  const triggerLabel = selectedItem?.label ?? "选择学科";
  const triggerRef = useRef<HTMLButtonElement>(null);
  const leaveTimer = useRef<number>(0);
  const [expanded, setExpanded] = useState(false);
  const [hoverMode, setHoverMode] = useState(true);
  const [coords, setCoords] = useState({ top: 0, left: 0 });

  useEffect(() => {
    const media = window.matchMedia("(hover: hover) and (pointer: fine)");
    const sync = () => setHoverMode(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => () => window.clearTimeout(leaveTimer.current), []);

  const place = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const width = 18 * 16;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    setCoords({ top: rect.top, left });
  };

  useLayoutEffect(() => {
    if (!expanded) return;
    place();
    const update = () => place();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [expanded]);

  const open = () => {
    window.clearTimeout(leaveTimer.current);
    place();
    setExpanded(true);
  };

  const closeSoon = () => {
    window.clearTimeout(leaveTimer.current);
    leaveTimer.current = window.setTimeout(() => setExpanded(false), 150);
  };

  const close = () => {
    window.clearTimeout(leaveTimer.current);
    setExpanded(false);
  };

  if (layout === "spread") {
    return (
      <Box
        className={[styles.spread, className].filter(Boolean).join(" ")}
        role="radiogroup"
        aria-label={ariaLabel}
      >
        {items.map((item) => (
          <SubjectChip
            key={item.value || "all"}
            item={item}
            selected={item.value === value}
            onSelect={() => {
              if (item.value !== value) onChange(item.value);
            }}
          />
        ))}
      </Box>
    );
  }

  const panel = expanded && typeof document !== "undefined"
    ? createPortal(
      <Box
        className={styles.panel}
        role="radiogroup"
        aria-label={ariaLabel}
        style={{
          "--oops-geometry-top": `${coords.top}px`,
          "--oops-geometry-left": `${coords.left}px`,
        } as CSSProperties}
        onMouseEnter={hoverMode ? open : undefined}
        onMouseLeave={hoverMode ? closeSoon : undefined}
      >
        {items.map((item) => (
          <SubjectChip
            key={item.value || "all"}
            item={item}
            selected={item.value === value}
            onSelect={() => {
              if (item.value !== value) onChange(item.value);
              close();
            }}
          />
        ))}
      </Box>,
      document.body,
    )
    : null;

  return (
    <Box className={[styles.shell, className].filter(Boolean).join(" ")}>
      <Box
        as="button"
        type="button"
        ref={triggerRef}
        className={styles.trigger}
        aria-haspopup="true"
        aria-expanded={expanded}
        onMouseEnter={hoverMode ? open : undefined}
        onMouseLeave={hoverMode ? closeSoon : undefined}
        onFocus={open}
        onClick={() => {
          if (!hoverMode) {
            if (expanded) close();
            else open();
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
        }}
      >
        {triggerLabel}
      </Box>
      {panel}
    </Box>
  );
}
