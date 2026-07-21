"use client";

import {
  ActionIcon,
  Alert,
  Badge,
  Button as MantineButton,
  Checkbox as MantineCheckbox,
  Loader,
  Select as MantineSelect,
  Switch,
  Text as MantineText,
  Textarea as MantineTextarea,
  TextInput as MantineTextInput,
  Title,
  Tooltip as MantineTooltip,
} from "@mantine/core";
import React, { forwardRef, useEffect, useMemo } from "react";

export type SxProps = Record<string, unknown> | undefined;

const breakpoints = ["544px", "768px", "1024px", "1280px"];
const spacing = [0, 4, 8, 16, 24, 32, 40, 48, 64];
const fontSizes = ["12px", "14px", "16px", "20px", "24px", "32px", "40px"];

const tokenMap: Record<string, string> = {
  "fg.default": "var(--fgColor-default)",
  "fg.muted": "var(--fgColor-muted)",
  "fg.accent": "var(--fgColor-accent)",
  "fg.success": "var(--fgColor-success)",
  "fg.danger": "var(--fgColor-danger)",
  "fg.attention": "var(--fgColor-attention)",
  "accent.fg": "var(--fgColor-accent)",
  "accent.emphasis": "var(--fgColor-accent-emphasis)",
  "accent.subtle": "var(--bgColor-accent-muted)",
  "canvas.default": "var(--bgColor-default)",
  "canvas.subtle": "var(--bgColor-muted)",
  "canvas.overlay": "var(--bgColor-overlay)",
  "bg.default": "var(--bgColor-default)",
  "bg.muted": "var(--bgColor-muted)",
  "border.default": "var(--borderColor-default)",
  "border.muted": "var(--borderColor-muted)",
  "border.accent-emphasis": "var(--fgColor-accent)",
  "danger.fg": "var(--fgColor-danger)",
  "danger.emphasis": "var(--fgColor-danger-emphasis)",
  "danger.subtle": "var(--bgColor-danger-muted)",
  "success.fg": "var(--fgColor-success)",
  "success.subtle": "var(--bgColor-success-muted)",
  "attention.fg": "var(--fgColor-attention)",
  "attention.subtle": "var(--bgColor-attention-muted)",
  "shadow.small": "var(--oops-shadow-sm)",
  "shadow.medium": "var(--oops-shadow-md)",
};

function resolveToken(value: unknown): string | number | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return value as number;
  return tokenMap[value] ?? value;
}

function spacingValue(value: unknown): string | number | undefined {
  if (typeof value !== "number") return resolveToken(value);
  return spacing[value] ?? value;
}

function fontSizeValue(value: unknown): string | number | undefined {
  if (typeof value !== "number") return resolveToken(value);
  return fontSizes[value] ?? value;
}

function normalizeProperty(property: string): string {
  const aliases: Record<string, string> = {
    bg: "backgroundColor",
    m: "margin",
    mt: "marginTop",
    mr: "marginRight",
    mb: "marginBottom",
    ml: "marginLeft",
    mx: "marginInline",
    my: "marginBlock",
    p: "padding",
    pt: "paddingTop",
    pr: "paddingRight",
    pb: "paddingBottom",
    pl: "paddingLeft",
    px: "paddingInline",
    py: "paddingBlock",
  };
  return aliases[property] ?? property;
}

function normalizeValue(property: string, value: unknown): string | number | undefined {
  const normalized = normalizeProperty(property);
  if (["margin", "marginTop", "marginRight", "marginBottom", "marginLeft", "marginInline", "marginBlock", "padding", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "paddingInline", "paddingBlock", "gap", "rowGap", "columnGap"].includes(normalized)) {
    return spacingValue(value);
  }
  if (normalized === "fontSize") return fontSizeValue(value);
  if (typeof value === "string" && value === "mono") {
    return "var(--font-mono)";
  }
  return resolveToken(value);
}

function cssProperty(property: string): string {
  return normalizeProperty(property).replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
}

function cssValue(property: string, value: unknown): string {
  const normalized = normalizeValue(property, value);
  if (normalized === undefined) return "";
  if (typeof normalized === "number" && !["opacity", "zIndex", "fontWeight", "lineHeight", "flex", "order", "zoom"].includes(normalizeProperty(property))) {
    return `${normalized}px`;
  }
  return String(normalized);
}

function hashSx(sx: SxProps): string {
  const source = JSON.stringify(sx ?? {});
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `oops-sx-${(hash >>> 0).toString(36)}`;
}

function selectorFor(parent: string, key: string): string {
  if (key.includes("&")) return key.replaceAll("&", `.${parent}`);
  if (key.startsWith(":")) return `.${parent}${key}`;
  return `.${parent} ${key}`;
}

function rulesFor(sx: Record<string, unknown>, selector: string, media?: string): string {
  const declarations: string[] = [];
  const nested: string[] = [];
  for (const [property, rawValue] of Object.entries(sx)) {
    if (rawValue === undefined || rawValue === null) continue;
    if (property.startsWith("@media")) {
      nested.push(`${property}{${rulesFor(rawValue as Record<string, unknown>, selector)}}`);
      continue;
    }
    if (property.startsWith("&") || property.startsWith(":" ) || property === "input" || property === "textarea" || property === "button" || property === "svg") {
      nested.push(rulesFor(rawValue as Record<string, unknown>, selectorFor(selector.slice(1), property)));
      continue;
    }
    if (Array.isArray(rawValue)) {
      const first = rawValue[0];
      if (first !== undefined) declarations.push(`${cssProperty(property)}:${cssValue(property, first)};`);
      rawValue.slice(1).forEach((value, index) => {
        if (value === undefined) return;
        const rule = rulesFor({ [property]: value }, selector);
        nested.push(`@media (min-width: ${breakpoints[index]}){${rule}}`);
      });
      continue;
    }
    if (typeof rawValue === "object") {
      nested.push(rulesFor(rawValue as Record<string, unknown>, selectorFor(selector.slice(1), property)));
      continue;
    }
    declarations.push(`${cssProperty(property)}:${cssValue(property, rawValue)};`);
  }
  const current = declarations.length ? `${selector}{${declarations.join("")}}` : "";
  return `${media ? `${media}{` : ""}${current}${nested.join("")}${media ? "}" : ""}`;
}

function baseStyle(sx: SxProps): React.CSSProperties {
  const style: Record<string, string | number> = {};
  for (const [property, rawValue] of Object.entries(sx ?? {})) {
    if (property.startsWith("&") || property.startsWith(":" ) || property.startsWith("@") || ["input", "textarea", "button", "svg"].includes(property)) continue;
    // Responsive arrays are emitted as class rules; an inline mobile value
    // would have higher specificity and prevent desktop media queries winning.
    if (Array.isArray(rawValue)) continue;
    const value = rawValue;
    if (value === undefined || typeof value === "object") continue;
    style[normalizeProperty(property)] = normalizeValue(property, value) as string | number;
  }
  return style as React.CSSProperties;
}

function useSx(sx: SxProps) {
  const className = useMemo(() => (sx && Object.keys(sx).length ? hashSx(sx) : ""), [sx]);
  useEffect(() => {
    if (!className || !sx || typeof document === "undefined") return;
    if (document.head.querySelector(`style[data-oops-sx="${className}"]`)) return;
    const style = document.createElement("style");
    style.dataset.oopsSx = className;
    style.textContent = rulesFor(sx, `.${className}`);
    document.head.appendChild(style);
  }, [className, sx]);
  return { className, style: baseStyle(sx) };
}

type BoxProps = React.HTMLAttributes<HTMLElement> & React.ImgHTMLAttributes<HTMLImageElement> & {
  as?: React.ElementType;
  sx?: SxProps;
  block?: boolean;
  type?: "button" | "submit" | "reset";
  href?: string;
};

export const Box = forwardRef<any, BoxProps>(function Box({ as, sx, className, block, style, ...props }, ref) {
  const resolved = useSx(sx);
  const Component = as ?? "div";
  return React.createElement(Component, {
    ...props,
    ref,
    className: [resolved.className, className].filter(Boolean).join(" ") || undefined,
    style: { ...resolved.style, ...(block ? { width: "100%" } : {}), ...style },
  });
});

type TextProps = React.HTMLAttributes<HTMLElement> & { sx?: SxProps; as?: React.ElementType; size?: string | number; fw?: number | string };
export const Text = forwardRef<any, TextProps>(function Text({ sx, className, style, as, size, fw, ...props }, ref) {
  const resolved = useSx(sx);
  return <MantineText ref={ref} component={as as any} size={size as any} fw={fw as any} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} {...props as any} />;
});

type HeadingProps = React.HTMLAttributes<HTMLHeadingElement> & { sx?: SxProps; as?: React.ElementType; order?: number };
export const Heading = forwardRef<any, HeadingProps>(function Heading({ sx, className, style, as, order = 1, ...props }, ref) {
  const resolved = useSx(sx);
  const component = as ?? `h${order}`;
  return <Title ref={ref} component={component as any} order={order as any} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} {...props as any} />;
});

type ButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { sx?: SxProps; leadingVisual?: React.ElementType; block?: boolean; variant?: string; size?: "small" | "medium" | "large" | "small"; color?: string };
export const Button = forwardRef<HTMLButtonElement, ButtonCompatProps>(function Button({ sx, className, style, variant, size = "medium", leadingVisual: LeadingVisual, block, color, ...props }, ref) {
  const resolved = useSx(sx);
  const mappedVariant = variant === "primary" ? "filled" : variant === "invisible" ? "subtle" : variant === "danger" ? "filled" : variant === "secondary" ? "light" : variant === "default" ? "default" : variant;
  return <MantineButton ref={ref} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} variant={mappedVariant as any} color={color ?? (variant === "danger" ? "red" : undefined)} size={size === "small" ? "xs" : size === "large" ? "md" : "sm"} fullWidth={block} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} {...props as any} />;
});

type IconButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { sx?: SxProps; icon?: React.ElementType; as?: React.ElementType; href?: string; variant?: string; size?: "small" | "medium" | "large" };
export const IconButton = forwardRef<HTMLButtonElement, IconButtonCompatProps>(function IconButton({ sx, className, style, icon: Icon, variant, size = "medium", as, ...props }, ref) {
  const resolved = useSx(sx);
  const mappedVariant = variant === "invisible" ? "subtle" : variant === "default" ? "light" : variant;
  return <ActionIcon ref={ref} component={as as any} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} variant={mappedVariant as any} size={size === "small" ? "sm" : size === "large" ? "lg" : "md"} {...props as any}>{Icon ? <Icon size={16} /> : props.children}</ActionIcon>;
});

type TextInputCompatProps = React.InputHTMLAttributes<HTMLInputElement> & { sx?: SxProps; block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode; monospace?: boolean; leadingVisual?: React.ElementType };
export const TextInput = forwardRef<HTMLDivElement, TextInputCompatProps>(function TextInput({ sx, className, style, block, monospace, leadingVisual: LeadingVisual, ...props }, ref) {
  const resolved = useSx(sx);
  return <div ref={ref} className={["oops-input-wrap", resolved.className, className].filter(Boolean).join(" ")} style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }}><MantineTextInput {...props as any} w={block ? "100%" : undefined} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} styles={monospace ? { input: { fontFamily: "var(--font-mono)" } } : undefined} /></div>;
});

type TextareaCompatProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & { sx?: SxProps; block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode };
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaCompatProps>(function Textarea({ sx, className, style, block, ...props }, ref) {
  const resolved = useSx(sx);
  return <MantineTextarea ref={ref} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }} w={block ? "100%" : undefined} {...props as any} />;
});

type SelectCompatProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size"> & { sx?: SxProps; block?: boolean };
export const Select = Object.assign(forwardRef<HTMLSelectElement, SelectCompatProps>(function Select({ sx, className, style, block, ...props }, ref) {
  const resolved = useSx(sx);
  return <select ref={ref} className={["oops-native-select", resolved.className, className].filter(Boolean).join(" ")} style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }} {...props} />;
}), { Option: "option" as const });

type FormControlProps = React.HTMLAttributes<HTMLDivElement> & { sx?: SxProps };
function FormControlComponent({ sx, className, style, ...props }: FormControlProps) {
  const resolved = useSx(sx);
  return <div className={["oops-form-control", resolved.className, className].filter(Boolean).join(" ")} style={{ ...resolved.style, ...style }} {...props} />;
}
const FormControlLabel = ({ children, visuallyHidden, ...props }: React.LabelHTMLAttributes<HTMLLabelElement> & { visuallyHidden?: boolean }) => <label className={visuallyHidden ? "oops-visually-hidden" : "oops-field-label"} {...props}>{children}</label>;
const FormControlCaption = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="oops-field-caption" {...props}>{children}</div>;
export const FormControl = Object.assign(FormControlComponent, { Label: FormControlLabel, Caption: FormControlCaption });

type LabelCompatProps = React.HTMLAttributes<HTMLDivElement> & { sx?: SxProps; variant?: string; size?: string };
export const Label = forwardRef<HTMLDivElement, LabelCompatProps>(function Label({ sx, className, style, variant = "secondary", ...props }, ref) {
  const resolved = useSx(sx);
  const mapped = variant === "danger" ? "light" : variant === "accent" ? "light" : variant === "success" ? "light" : variant === "warning" ? "light" : variant === "primary" ? "filled" : "default";
  const color = variant === "danger" ? "red" : variant === "success" ? "green" : variant === "warning" ? "yellow" : variant === "accent" ? "teal" : undefined;
  return <Badge ref={ref} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} variant={mapped as any} color={color} {...props as any} />;
});

type SpinnerCompatProps = React.HTMLAttributes<HTMLDivElement> & { size?: number | string | "small" | "medium" | "large"; sx?: SxProps; color?: string };
export function Spinner({ sx, className, style, size = "medium", ...props }: SpinnerCompatProps) {
  const resolved = useSx(sx);
  const loaderSize = size === "small" ? 16 : size === "large" ? 28 : size === "medium" ? 22 : size;
  return <Loader className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} size={loaderSize} {...props as any} />;
}

export const Checkbox = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { label?: React.ReactNode }>(function Checkbox(props, ref) { return <MantineCheckbox ref={ref} {...props as any} />; });
type ToggleSwitchProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & { size?: "small" | "medium" | "large"; sx?: SxProps };
export const ToggleSwitch = forwardRef<HTMLInputElement, ToggleSwitchProps>(function ToggleSwitch({ size = "small", sx, ...props }, ref) { return <Switch ref={ref} size={size === "small" ? "sm" : size === "large" ? "lg" : "md"} {...props as any} />; });
export const ButtonGroup = ({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={["oops-button-group", className].filter(Boolean).join(" ")} {...props}>{children}</div>;

type TooltipCompatProps = React.HTMLAttributes<HTMLDivElement> & { text: React.ReactNode; direction?: string };
export function Tooltip({ text, direction, children, ...props }: TooltipCompatProps) {
  const position = direction === "s" ? "bottom" : direction === "e" ? "right" : direction === "w" ? "left" : "top";
  return <MantineTooltip label={text} position={position} {...props}>{children}</MantineTooltip>;
}

type FlashProps = React.HTMLAttributes<HTMLDivElement> & { variant?: string; color?: string };
export function Flash({ variant = "default", color, ...props }: FlashProps) {
  return <Alert color={color ?? (variant === "danger" ? "red" : variant === "success" ? "green" : "teal")} {...props as any} />;
}

export const Octicon = ({ icon: Icon, size = 16, ...props }: { icon: React.ElementType; size?: number; sx?: SxProps }) => <Icon size={size} {...props} />;

const NavListComponent = ({ children, className, sx, ...props }: BoxProps) => <Box className={["oops-nav-list", className].filter(Boolean).join(" ")} sx={sx} {...props}>{children}</Box>;
const NavListItem = ({ children, className, sx, as, ...props }: BoxProps & { href?: string; "aria-current"?: string }) => <Box as={as ?? "a"} className={["oops-nav-item", className].filter(Boolean).join(" ")} sx={sx} {...props}>{children}</Box>;
const NavListLeadingVisual = ({ children }: { children: React.ReactNode }) => <span className="oops-nav-leading">{children}</span>;
export const NavList = Object.assign(NavListComponent, { Item: NavListItem, LeadingVisual: NavListLeadingVisual });
