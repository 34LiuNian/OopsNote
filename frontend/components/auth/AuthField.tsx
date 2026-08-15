"use client";

import { ReactNode, useId } from "react";
import type { ComponentType } from "react";
import { PasswordInput, TextInput } from "@/components/ui/primitives";
import styles from "./AuthField.module.css";

type AuthFieldProps = {
  label: string;
  labelSuffix?: ReactNode;
  description?: string;
  icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  error?: string | null;
  type?: "text" | "email" | "password";
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  name?: string;
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  placeholder?: string;
  autoFocus?: boolean;
};

export function AuthField({
  label,
  labelSuffix,
  description,
  icon: Icon,
  error,
  type = "text",
  value,
  onChange,
  onBlur,
  name,
  autoComplete,
  required,
  minLength,
  maxLength,
  pattern,
  placeholder,
  autoFocus,
}: AuthFieldProps) {
  const fieldId = useId();
  const descriptionId = description ? `${fieldId}-description` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(" ") || undefined;

  const shared = {
    id: fieldId,
    name,
    value,
    variant: "unstyled" as const,
    autoComplete,
    required,
    minLength,
    maxLength,
    placeholder,
    autoFocus,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
    onChange: (event: { target: { value: string } }) => onChange(event.target.value),
    onBlur,
  };

  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label className={styles.label} htmlFor={fieldId}>{label}</label>
        {labelSuffix}
      </div>
      {description ? <p id={descriptionId} className={styles.description}>{description}</p> : null}
      <div className={styles.control} data-error={error ? "true" : undefined}>
        <span className={styles.icon}><Icon size={16} aria-hidden /></span>
        {type === "password" ? (
          <PasswordInput {...shared} />
        ) : (
          <TextInput {...shared} type={type} pattern={pattern} />
        )}
      </div>
      {error ? <p id={errorId} className={styles.error}>{error}</p> : null}
    </div>
  );
}
