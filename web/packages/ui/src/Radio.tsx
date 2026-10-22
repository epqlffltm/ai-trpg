// web/packages/ui/src/Radio.tsx
// 이름표가 붙은 라디오 단추 하나. 이름표 아래에 설명을 둘 수 있다. 같은 name 끼리 하나만 고른다.
// 모양은 체크 상자와 같다(ui-checkbox). 무엇을 골랐는지는 쓰는 쪽이 checked 로 정한다.

import { useId, type InputHTMLAttributes, type ReactNode } from 'react';

export type RadioProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label: ReactNode;
  description?: ReactNode;
};

export function Radio({ label, description, id, ...rest }: RadioProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const descriptionId = `${inputId}-description`;
  return (
    <div className="ui-checkbox">
      <input
        {...rest}
        id={inputId}
        type="radio"
        className="ui-checkbox__input"
        aria-describedby={description ? descriptionId : undefined}
      />
      <label htmlFor={inputId} className="ui-checkbox__label">
        {label}
      </label>
      {description ? (
        <p id={descriptionId} className="ui-checkbox__description">
          {description}
        </p>
      ) : null}
    </div>
  );
}
