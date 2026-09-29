// 공통 버튼 (NAME-F01) — docs/9-style-guide.md §5.1
import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react';
import './Button.css';

export type ButtonVariant =
  | 'primary-pill'
  | 'primary-square'
  | 'outline-pill'
  | 'outline-square'
  | 'tag-visited'
  | 'tag-hold'
  | 'tag-rejected'
  | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

export function Button({ variant = 'primary-pill', className, children, type = 'button', ...rest }: ButtonProps) {
  const classes = ['btn', `btn--${variant}`, className].filter(Boolean).join(' ');
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  );
}
