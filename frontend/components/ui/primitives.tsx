"use client";

import {
  ActionIcon,
  Alert as MantineAlert,
  Avatar as MantineAvatar,
  Badge,
  Button as MantineButton,
  Checkbox as MantineCheckbox,
  Collapse as MantineCollapse,
  Drawer as MantineDrawer,
  Group as MantineGroup,
  Loader,
  Menu as MantineMenu,
  Modal as MantineModal,
  PasswordInput as MantinePasswordInput,
  Select as MantineSelect,
  Stack as MantineStack,
  Switch,
  Text as MantineText,
  Textarea as MantineTextarea,
  TextInput as MantineTextInput,
  Title,
  Tooltip as MantineTooltip,
} from "@mantine/core";
import React, { forwardRef, useEffect, useMemo } from "react";
export { useReducedMotion } from "@mantine/hooks";
export { modals } from "@mantine/modals";

type ResponsiveSxValue<T> = T | readonly (T | undefined)[];
type SxSpaceAlias = "bg" | "m" | "mt" | "mr" | "mb" | "ml" | "mx" | "my" | "p" | "pt" | "pr" | "pb" | "pl" | "px" | "py";
type SxNestedSelector = `&${string}` | `:${string}` | `@media ${string}` | `@keyframes ${string}` | `${number}%` | "from" | "to" | "input" | "textarea" | "button" | "svg";

/** @deprecated Use semantic props, component variants, or feature geometry classes. */
export type SxProps = {
  [property in keyof React.CSSProperties]?: ResponsiveSxValue<React.CSSProperties[property]>;
} & {
  [property in SxSpaceAlias]?: ResponsiveSxValue<string | number>;
} & {
  [selector in SxNestedSelector]?: SxProps;
} | undefined;

const breakpoints = ["544px", "768px", "1024px", "1280px"];
const spacing = [
  "var(--oops-space-0)",
  "var(--oops-space-1)",
  "var(--oops-space-2)",
  "var(--oops-space-4)",
  "var(--oops-space-5)",
  "var(--oops-space-6)",
  "var(--oops-space-7)",
  "var(--oops-space-8)",
  "var(--oops-space-9)",
];
const fontSizes = [
  "var(--oops-text-xs)",
  "var(--oops-text-sm)",
  "var(--oops-text-md)",
  "var(--oops-text-lg)",
  "var(--oops-text-xl)",
  "var(--oops-text-2xl)",
  "var(--oops-text-3xl)",
];

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

function rulesFor(sx: Exclude<SxProps, undefined>, selector: string, media?: string): string {
  const declarations: string[] = [];
  const nested: string[] = [];
  for (const [property, rawValue] of Object.entries(sx)) {
    if (rawValue === undefined || rawValue === null) continue;
    if (property.startsWith("@media")) {
      nested.push(`${property}{${rulesFor(rawValue as Exclude<SxProps, undefined>, selector)}}`);
      continue;
    }
    if (property.startsWith("&") || property.startsWith(":" ) || property === "input" || property === "textarea" || property === "button" || property === "svg") {
      nested.push(rulesFor(rawValue as Exclude<SxProps, undefined>, selectorFor(selector.slice(1), property)));
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
      nested.push(rulesFor(rawValue as Exclude<SxProps, undefined>, selectorFor(selector.slice(1), property)));
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

type ButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { sx?: SxProps; leadingVisual?: React.ElementType; trailingVisual?: React.ElementType; block?: boolean; variant?: string; size?: "small" | "medium" | "large" | "small"; color?: string };
export const Button = forwardRef<HTMLButtonElement, ButtonCompatProps>(function Button({ sx, className, style, variant, size = "medium", leadingVisual: LeadingVisual, trailingVisual: TrailingVisual, block, color, ...props }, ref) {
  const resolved = useSx(sx);
  const mappedVariant = variant === "primary" ? "filled" : variant === "invisible" ? "subtle" : variant === "danger" ? "filled" : variant === "secondary" ? "light" : variant === "default" ? "default" : variant;
  return <MantineButton ref={ref} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} variant={mappedVariant as any} color={color ?? (variant === "danger" ? "red" : undefined)} size={size === "small" ? "xs" : size === "large" ? "md" : "sm"} fullWidth={block} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} rightSection={TrailingVisual ? <TrailingVisual size={15} /> : undefined} {...props as any} />;
});

type IconButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { sx?: SxProps; icon?: React.ElementType; as?: React.ElementType; href?: string; variant?: string; size?: "small" | "medium" | "large" };
export const IconButton = forwardRef<HTMLButtonElement, IconButtonCompatProps>(function IconButton({ sx, className, style, icon: Icon, variant, size = "medium", as, ...props }, ref) {
  const resolved = useSx(sx);
  const mappedVariant = variant === "invisible" ? "subtle" : variant === "default" ? "light" : variant;
  return <ActionIcon ref={ref} component={as as any} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...style }} variant={mappedVariant as any} size={size === "small" ? "sm" : size === "large" ? "lg" : "md"} {...props as any}>{Icon ? <Icon size={16} /> : props.children}</ActionIcon>;
});

type TextInputCompatProps = React.InputHTMLAttributes<HTMLInputElement> & { sx?: SxProps; block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode; monospace?: boolean; leadingVisual?: React.ElementType };
export const TextInput = forwardRef<HTMLInputElement, TextInputCompatProps>(function TextInput({ sx, className, style, block, monospace, leadingVisual: LeadingVisual, ...props }, ref) {
  const resolved = useSx(sx);
  return <div className={["oops-input-wrap", resolved.className, className].filter(Boolean).join(" ")} style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }}><MantineTextInput ref={ref} {...props as any} w={block ? "100%" : undefined} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} styles={monospace ? { input: { fontFamily: "var(--font-mono)" } } : undefined} /></div>;
});

type TextareaCompatProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & { sx?: SxProps; block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode };
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaCompatProps>(function Textarea({ sx, className, style, block, ...props }, ref) {
  const resolved = useSx(sx);
  return <MantineTextarea ref={ref} className={[resolved.className, className].filter(Boolean).join(" ") || undefined} style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }} w={block ? "100%" : undefined} {...props as any} />;
});

type SelectOptionProps = {
  children: React.ReactNode;
  disabled?: boolean;
  value: string;
};

function SelectOption(_props: SelectOptionProps) {
  return null;
}

function selectOptionLabel(node: React.ReactNode): string {
  return React.Children.toArray(node)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") return String(child);
      if (React.isValidElement<{ children?: React.ReactNode }>(child)) {
        return selectOptionLabel(child.props.children);
      }
      return "";
    })
    .join("");
}

type SelectCompatProps = {
  "aria-label"?: string;
  "aria-labelledby"?: string;
  autoFocus?: boolean;
  block?: boolean;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  form?: string;
  id?: string;
  label?: React.ReactNode;
  description?: React.ReactNode;
  error?: React.ReactNode;
  name?: string;
  onBlur?: React.FocusEventHandler<HTMLInputElement>;
  onFocus?: React.FocusEventHandler<HTMLInputElement>;
  onValueChange: (value: string) => void;
  required?: boolean;
  style?: React.CSSProperties;
  sx?: SxProps;
  tabIndex?: number;
  value: string;
};

export const Select = Object.assign(forwardRef<HTMLInputElement, SelectCompatProps>(function Select({
  block,
  children,
  className,
  onValueChange,
  style,
  sx,
  value,
  ...props
}, ref) {
  const resolved = useSx(sx);
  const options = React.Children.toArray(children)
    .filter((child): child is React.ReactElement<SelectOptionProps> => (
      React.isValidElement<SelectOptionProps>(child) && child.type === SelectOption
    ))
    .map((child, index) => ({
      disabled: child.props.disabled,
      externalValue: child.props.value,
      label: selectOptionLabel(child.props.children),
      value: `oops-select-option-${index}`,
    }));
  const selectedOption = options.find((option) => option.externalValue === value && !option.disabled)
    ?? options.find((option) => option.externalValue === value);

  return (
    <MantineSelect
      {...props}
      ref={ref}
      allowDeselect={false}
      className={[resolved.className, className].filter(Boolean).join(" ") || undefined}
      classNames={{
        dropdown: "oops-select-dropdown",
        input: "oops-select-input",
        option: "oops-select-option",
      }}
      comboboxProps={{ withinPortal: true }}
      data={options.map(({ disabled, label, value: optionValue }) => ({ disabled, label, value: optionValue }))}
      onChange={(nextValue) => {
        const option = options.find((candidate) => candidate.value === nextValue);
        if (option) onValueChange(option.externalValue);
      }}
      style={{ ...resolved.style, ...(block ? { width: "100%" } : {}), ...style }}
      value={selectedOption?.value ?? null}
      w={block ? "100%" : undefined}
    />
  );
}), { Option: SelectOption });

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
  return <MantineAlert color={color ?? (variant === "danger" ? "red" : variant === "success" ? "green" : "teal")} {...props as any} />;
}

export const Octicon = ({ icon: Icon, size = 16, ...props }: { icon: React.ElementType; size?: number; sx?: SxProps }) => <Icon size={size} {...props} />;

const NavListComponent = ({ children, className, sx, ...props }: BoxProps) => <Box className={["oops-nav-list", className].filter(Boolean).join(" ")} sx={sx} {...props}>{children}</Box>;
const NavListItem = ({ children, className, sx, as, ...props }: BoxProps & { href?: string; "aria-current"?: string }) => <Box as={as ?? "a"} className={["oops-nav-item", className].filter(Boolean).join(" ")} sx={sx} {...props}>{children}</Box>;
const NavListLeadingVisual = ({ children }: { children: React.ReactNode }) => <span className="oops-nav-leading">{children}</span>;
export const NavList = Object.assign(NavListComponent, { Item: NavListItem, LeadingVisual: NavListLeadingVisual });

// Mantine remains an implementation detail of the Oops UI facade. These aliases
// are intentionally exported from this module so feature code has one import boundary.
export const Avatar = MantineAvatar;
export const Collapse = MantineCollapse;
export const Drawer = MantineDrawer;
export const Group = MantineGroup;
export const Menu = MantineMenu;
export const Modal = MantineModal;
export const PasswordInput = MantinePasswordInput;
export const Stack = MantineStack;
export const Dialog = MantineModal;
export const Alert = MantineAlert;

export function Surface({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={["oops-surface", className].filter(Boolean).join(" ")} {...props} />;
}

type NativeInputProps = React.InputHTMLAttributes<HTMLInputElement> & { className?: string };
export const NativeInput = forwardRef<HTMLInputElement, NativeInputProps>(function NativeInput({ className, ...props }, ref) {
  return <input ref={ref} className={["oops-native-input", className].filter(Boolean).join(" ")} {...props} />;
});

type NativeSelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & { className?: string };
export const NativeSelect = forwardRef<HTMLSelectElement, NativeSelectProps>(function NativeSelect({ className, ...props }, ref) {
  return <select ref={ref} className={["oops-native-select", className].filter(Boolean).join(" ")} {...props} />;
});

type GeometryButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { className?: string };
export const GeometryButton = forwardRef<HTMLButtonElement, GeometryButtonProps>(function GeometryButton({ className, ...props }, ref) {
  return <button ref={ref} className={["oops-geometry-button", className].filter(Boolean).join(" ")} {...props} />;
});
