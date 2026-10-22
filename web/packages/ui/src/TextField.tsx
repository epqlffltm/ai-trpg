// web/packages/ui/src/TextField.tsx
// 이름표가 붙은 입력 칸 하나. 칸의 오류 글을 칸 아래에 보이고 입력 칸과 잇는다(aria-describedby).

import { useId, type InputHTMLAttributes } from 'react';

export type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  /** 서버나 화면이 알려 준 이 칸의 문제. 없으면 아무것도 보이지 않는다 */
  error?: string | undefined;
};

export function TextField({ label, error, id, ...rest }: TextFieldProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const errorId = `${inputId}-error`;
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={inputId}>
        {label}
      </label>
      <input
        {...rest}
        id={inputId}
        className="ui-field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />
      {error ? (
        <p id={errorId} className="ui-field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
