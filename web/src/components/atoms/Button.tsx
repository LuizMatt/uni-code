import React from "react";
import { Link } from "react-router-dom";
import buttonConfig from "../../config/buttonConfig.json";

export type ButtonVariant = keyof typeof buttonConfig.variants;
export type ButtonSize = keyof typeof buttonConfig.sizes;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: string;
  iconRight?: string;
  loading?: boolean;
  loadingText?: string;
  fullWidth?: boolean;
  to?: string;
}

export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  size = "md",
  icon,
  iconRight,
  loading = false,
  loadingText,
  fullWidth = false,
  to,
  disabled,
  className = "",
  type = "button",
  children,
  ...rest
}) => {
  const variantClass = buttonConfig.variants[variant] || buttonConfig.variants.primary;
  const sizeClass = buttonConfig.sizes[size] || buttonConfig.sizes.md;
  const widthClass = fullWidth ? "w-full" : "";
  const combinedClassName = `${buttonConfig.baseClass} ${variantClass} ${sizeClass} ${widthClass} ${className}`.trim();

  const content = (
    <>
      {loading ? (
        <i className="mdi mdi-loading animate-spin text-current leading-none" aria-hidden="true" />
      ) : icon ? (
        <i className={`mdi ${icon} leading-none`} aria-hidden="true" />
      ) : null}
      {loading && loadingText ? <span>{loadingText}</span> : children ? <span>{children}</span> : null}
      {!loading && iconRight ? (
        <i className={`mdi ${iconRight} leading-none`} aria-hidden="true" />
      ) : null}
    </>
  );

  if (to && !disabled && !loading) {
    const { onClick, id, title, tabIndex, "aria-label": ariaLabel } = rest;
    return (
      <Link
        to={to}
        id={id}
        title={title}
        tabIndex={tabIndex}
        aria-label={ariaLabel}
        onClick={onClick as unknown as React.MouseEventHandler<HTMLAnchorElement> | undefined}
        className={combinedClassName}
      >
        {content}
      </Link>
    );
  }

  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={combinedClassName}
      {...rest}
    >
      {content}
    </button>
  );
};
