// web/packages/ui/src/Button.tsx
// 버튼 하나. 모양(variant)과 "보내는 중" 표시만 정한다. 무엇을 할지는 쓰는 쪽이 onClick 이나 form 으로 정한다.

import type { ButtonHTMLAttributes } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  /** 요청을 보내는 중이면 누르지 못하게 하고 화면 읽기 프로그램에 알린다 */
  busy?: boolean;
};

export function Button({ variant = 'primary', busy = false, disabled, className, type, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      type={type ?? 'button'}
      className={['ui-button', `ui-button--${variant}`, className].filter(Boolean).join(' ')}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    />
  );
}
