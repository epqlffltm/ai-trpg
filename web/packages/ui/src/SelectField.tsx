// web/packages/ui/src/SelectField.tsx
// 이름표가 붙은 고르기 칸 하나. 칸의 오류 글을 칸 아래에 보이고 칸과 잇는다(aria-describedby). 입력 칸(TextField)과 모양이 같다.
// 고를 것(option)은 쓰는 쪽이 children 으로 넘긴다.

import { useId, type ReactNode, type SelectHTMLAttributes } from 'react';

export type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  /** 이 칸의 문제. 없으면 아무것도 보이지 않는다 */
  error?: string | undefined;
  /** 칸 아래의 짧은 설명 */
  hint?: ReactNode;
};

export function SelectField({ label, error, hint, id, children, ...rest }: SelectFieldProps) {
  const fallbackId = useId();
  const selectId = id ?? fallbackId;
  const errorId = `${selectId}-error`;
  const hintId = `${selectId}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={selectId}>
        {label}
      </label>
      <select
        {...rest}
        id={selectId}
        className="ui-field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      >
        {children}
      </select>
      {hint ? (
        <p id={hintId} className="ui-field__hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="ui-field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
