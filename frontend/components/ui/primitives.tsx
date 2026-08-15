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
  Loader,
  Menu as MantineMenu,
  Modal as MantineModal,
  PasswordInput as MantinePasswordInput,
  Select as MantineSelect,
  Switch,
  Text as MantineText,
  Textarea as MantineTextarea,
  TextInput as MantineTextInput,
  Title,
  Tooltip as MantineTooltip,
} from "@mantine/core";
import React, { forwardRef } from "react";
import layoutStyles from "./layout.module.css";
export { useReducedMotion } from "@mantine/hooks";
export { modals } from "@mantine/modals";

type BoxProps = React.HTMLAttributes<HTMLElement> & React.ImgHTMLAttributes<HTMLImageElement> & {
  as?: React.ElementType;
  block?: boolean;
  type?: "button" | "submit" | "reset";
  href?: string;
};

export const Box = forwardRef<any, BoxProps>(function Box({ as, className, block, style, ...props }, ref) {
  const Component = as ?? "div";
  return React.createElement(Component, {
    ...props,
    ref,
    className: ["oops-box", className].filter(Boolean).join(" ") || undefined,
    style: { ...(block ? { width: "100%" } : {}), ...style },
  });
});

const cap = (value: string) => `${value[0].toUpperCase()}${value.slice(1)}`;

type TextSize = "xs" | "sm" | "md" | "lg" | "xl";
type TextTone = "default" | "muted" | "accent" | "success" | "danger" | "attention";
type TextWeight = "regular" | "medium" | "semibold" | "bold";
type TextProps = React.HTMLAttributes<HTMLElement> & { as?: React.ElementType; size?: TextSize | string | number; fw?: number | string; tone?: TextTone; weight?: TextWeight; family?: "sans" | "mono"; truncate?: boolean };
export const Text = forwardRef<any, TextProps>(function Text({ className, style, as, size, fw, tone = "default", weight = "regular", family = "sans", truncate = false, ...props }, ref) {
  const semanticSize = typeof size === "string" && ["xs", "sm", "md", "lg", "xl"].includes(size) ? layoutStyles[`text${cap(size)}` as keyof typeof layoutStyles] : undefined;
  return <MantineText ref={ref} component={as as any} size={semanticSize ? undefined : size as any} fw={fw as any} className={["oops-text", semanticSize, tone !== "default" ? layoutStyles[`tone${cap(tone)}` as keyof typeof layoutStyles] : undefined, weight !== "regular" ? layoutStyles[`weight${cap(weight)}` as keyof typeof layoutStyles] : undefined, family === "mono" ? layoutStyles.familyMono : undefined, truncate ? layoutStyles.truncate : undefined, className].filter(Boolean).join(" ") || undefined} style={style} {...props as any} />;
});

type HeadingProps = React.HTMLAttributes<HTMLHeadingElement> & { as?: React.ElementType; order?: number };
export const Heading = forwardRef<any, HeadingProps>(function Heading({ className, style, as, order = 1, ...props }, ref) {
  const component = as ?? `h${order}`;
  return <Title ref={ref} component={component as any} order={order as any} className={["oops-heading", className].filter(Boolean).join(" ")} style={style} {...props as any} />;
});

type ButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { leadingVisual?: React.ElementType; trailingVisual?: React.ElementType; block?: boolean; variant?: string; size?: "small" | "medium" | "large" | "small"; color?: string };
export const Button = forwardRef<HTMLButtonElement, ButtonCompatProps>(function Button({ className, style, variant, size = "medium", leadingVisual: LeadingVisual, trailingVisual: TrailingVisual, block, color, ...props }, ref) {
  const mappedVariant = variant === "primary" ? "filled" : variant === "invisible" ? "subtle" : variant === "danger" ? "filled" : variant === "secondary" ? "light" : variant === "default" ? "default" : variant;
  return <MantineButton ref={ref} className={["oops-button", className].filter(Boolean).join(" ")} style={style} variant={mappedVariant as any} color={color ?? (variant === "danger" ? "red" : undefined)} size={size === "small" ? "xs" : size === "large" ? "md" : "sm"} fullWidth={block} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} rightSection={TrailingVisual ? <TrailingVisual size={15} /> : undefined} {...props as any} />;
});

type IconButtonCompatProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { icon?: React.ElementType; as?: React.ElementType; href?: string; variant?: string; size?: "small" | "medium" | "large" };
export const IconButton = forwardRef<HTMLButtonElement, IconButtonCompatProps>(function IconButton({ className, style, icon: Icon, variant, size = "medium", as, ...props }, ref) {
  const mappedVariant = variant === "invisible" ? "subtle" : variant === "default" ? "light" : variant;
  return <ActionIcon ref={ref} component={as as any} className={["oops-icon-button", className].filter(Boolean).join(" ")} style={style} variant={mappedVariant as any} size={size === "small" ? "sm" : size === "large" ? "lg" : "md"} {...props as any}>{Icon ? <Icon size={16} /> : props.children}</ActionIcon>;
});

type TextInputCompatProps = React.InputHTMLAttributes<HTMLInputElement> & { block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode; monospace?: boolean; leadingVisual?: React.ElementType };
export const TextInput = forwardRef<HTMLInputElement, TextInputCompatProps>(function TextInput({ className, style, block, monospace, leadingVisual: LeadingVisual, ...props }, ref) {
  return <div className={["oops-input-wrap", className].filter(Boolean).join(" ")} style={{ ...(block ? { width: "100%" } : {}), ...style }}><MantineTextInput ref={ref} {...props as any} w={block ? "100%" : undefined} leftSection={LeadingVisual ? <LeadingVisual size={15} /> : undefined} styles={monospace ? { input: { fontFamily: "var(--font-mono)" } } : undefined} /></div>;
});

type TextareaCompatProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & { block?: boolean; label?: React.ReactNode; description?: React.ReactNode; error?: React.ReactNode };
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaCompatProps>(function Textarea({ className, style, block, ...props }, ref) {
  return <MantineTextarea ref={ref} className={["oops-textarea", className].filter(Boolean).join(" ")} style={{ ...(block ? { width: "100%" } : {}), ...style }} w={block ? "100%" : undefined} {...props as any} />;
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
  tabIndex?: number;
  value: string;
};

export const Select = Object.assign(forwardRef<HTMLInputElement, SelectCompatProps>(function Select({
  block,
  children,
  className,
  onValueChange,
  style,
  value,
  ...props
}, ref) {
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
      className={["oops-select", className].filter(Boolean).join(" ")}
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
      style={{ ...(block ? { width: "100%" } : {}), ...style }}
      value={selectedOption?.value ?? null}
      w={block ? "100%" : undefined}
    />
  );
}), { Option: SelectOption });

type FormControlProps = React.HTMLAttributes<HTMLDivElement>;
function FormControlComponent({ className, style, ...props }: FormControlProps) {
  return <div className={["oops-form-control", className].filter(Boolean).join(" ")} style={style} {...props} />;
}
const FormControlLabel = ({ children, visuallyHidden, ...props }: React.LabelHTMLAttributes<HTMLLabelElement> & { visuallyHidden?: boolean }) => <label className={visuallyHidden ? "oops-visually-hidden" : "oops-field-label"} {...props}>{children}</label>;
const FormControlCaption = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="oops-field-caption" {...props}>{children}</div>;
export const FormControl = Object.assign(FormControlComponent, { Label: FormControlLabel, Caption: FormControlCaption });

type LabelCompatProps = React.HTMLAttributes<HTMLDivElement> & { variant?: string; size?: string };
export const Label = forwardRef<HTMLDivElement, LabelCompatProps>(function Label({ className, style, variant = "secondary", ...props }, ref) {
  const mapped = variant === "danger" ? "light" : variant === "accent" ? "light" : variant === "success" ? "light" : variant === "warning" ? "light" : variant === "primary" ? "filled" : "default";
  const color = variant === "danger" ? "red" : variant === "success" ? "green" : variant === "warning" ? "yellow" : variant === "accent" ? "teal" : undefined;
  return <Badge ref={ref} className={className} style={style} variant={mapped as any} color={color} {...props as any} />;
});

type SpinnerCompatProps = React.HTMLAttributes<HTMLDivElement> & { size?: number | string | "small" | "medium" | "large"; color?: string };
export function Spinner({ className, style, size = "medium", ...props }: SpinnerCompatProps) {
  const loaderSize = size === "small" ? 16 : size === "large" ? 28 : size === "medium" ? 22 : size;
  return <Loader className={className} style={style} size={loaderSize} {...props as any} />;
}

export const Checkbox = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { label?: React.ReactNode }>(function Checkbox(props, ref) { return <MantineCheckbox ref={ref} {...props as any} />; });
type ToggleSwitchProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & { size?: "small" | "medium" | "large" };
export const ToggleSwitch = forwardRef<HTMLInputElement, ToggleSwitchProps>(function ToggleSwitch({ size = "small", ...props }, ref) { return <Switch ref={ref} size={size === "small" ? "sm" : size === "large" ? "lg" : "md"} {...props as any} />; });
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

export const Octicon = ({ icon: Icon, size = 16, className, ...props }: { icon: React.ElementType; size?: number; className?: string }) => <Icon size={size} className={className} {...props} />;

const NavListComponent = ({ children, className, ...props }: BoxProps) => <Box className={["oops-nav-list", className].filter(Boolean).join(" ")} {...props}>{children}</Box>;
const NavListItem = ({ children, className, as, ...props }: BoxProps & { href?: string; "aria-current"?: string }) => <Box as={as ?? "a"} className={["oops-nav-item", className].filter(Boolean).join(" ")} {...props}>{children}</Box>;
const NavListLeadingVisual = ({ children }: { children: React.ReactNode }) => <span className="oops-nav-leading">{children}</span>;
export const NavList = Object.assign(NavListComponent, { Item: NavListItem, LeadingVisual: NavListLeadingVisual });

// Mantine remains an implementation detail of the Oops UI facade. These aliases
// are intentionally exported from this module so feature code has one import boundary.
export const Avatar = MantineAvatar;
export const Collapse = MantineCollapse;
export const Drawer = MantineDrawer;
export const Menu = MantineMenu;
export const Modal = MantineModal;
export const PasswordInput = MantinePasswordInput;
export const Dialog = MantineModal;
export const Alert = MantineAlert;

type Space = "xs" | "sm" | "md" | "lg" | "xl";
type Align = "start" | "center" | "end" | "stretch" | "baseline";
type Justify = "start" | "center" | "end" | "between";
type LayoutProps = React.HTMLAttributes<HTMLDivElement> & { gap?: Space; align?: Align; justify?: Justify; wrap?: boolean };

function layoutClass(kind: "stack" | "inline", { gap = "md", align = "stretch", justify = "start", wrap = false, className }: LayoutProps) {
  return [layoutStyles[kind], layoutStyles[`gap${cap(gap)}` as keyof typeof layoutStyles], layoutStyles[`align${cap(align)}` as keyof typeof layoutStyles], layoutStyles[`justify${cap(justify)}` as keyof typeof layoutStyles], wrap ? layoutStyles.wrap : undefined, className].filter(Boolean).join(" ");
}

export const Stack = forwardRef<HTMLDivElement, LayoutProps>(function Stack(props, ref) {
  const { gap, align, justify, wrap, className, ...rest } = props;
  return <div ref={ref} className={layoutClass("stack", { gap, align, justify, wrap, className })} {...rest} />;
});

export const Inline = forwardRef<HTMLDivElement, LayoutProps>(function Inline(props, ref) {
  const { gap, align, justify, wrap, className, ...rest } = props;
  return <div ref={ref} className={layoutClass("inline", { gap, align, justify, wrap, className })} {...rest} />;
});

export const Group = Inline;

type SurfaceProps = React.HTMLAttributes<HTMLDivElement> & { variant?: "plain" | "bordered" | "muted" | "elevated"; padding?: "none" | Space; radius?: "none" | "sm" | "md" | "lg" };
export function Surface({ className, variant = "plain", padding = "none", radius = "none", ...props }: SurfaceProps) {
  return <div className={["oops-surface", layoutStyles.surface, variant !== "plain" ? layoutStyles[`surface${cap(variant)}` as keyof typeof layoutStyles] : undefined, padding !== "none" ? layoutStyles[`padding${cap(padding)}` as keyof typeof layoutStyles] : undefined, radius !== "none" ? layoutStyles[`radius${cap(radius)}` as keyof typeof layoutStyles] : undefined, className].filter(Boolean).join(" ")} {...props} />;
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
