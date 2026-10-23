// web/apps/web/src/components/TextAreaField.tsx
// 이름표가 붙은 여러 줄 입력 칸 하나. 입력 칸(@ai-trpg/ui 의 TextField)과 모양이 같고, 칸 아래에 설명과 오류 글을 둔다.
// 공통 구성요소로 옮기는 것은 시안(Stitch)을 받을 때 함께 한다.

import { useId, type ReactNode, type TextareaHTMLAttributes } from 'react';

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  error?: string | undefined;
  hint?: ReactNode;
};

export function TextAreaField({ label, error, hint, id, ...rest }: Props) {
  const fallbackId = useId();
  const fieldId = id ?? fallbackId;
  const errorId = `${fieldId}-error`;
  const hintId = `${fieldId}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={fieldId}>
        {label}
      </label>
      <textarea {...rest} id={fieldId} className="ui-field__input" aria-invalid={error ? true : undefined} aria-describedby={describedBy} />
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
