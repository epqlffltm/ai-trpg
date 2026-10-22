// web/packages/ui/src/Checkbox.tsx
// 이름표가 붙은 체크 상자 하나. 이름표 아래에 한 줄 설명을 둘 수 있다. 미리 체크하지 않는다(쓰는 쪽이 checked 를 정한다).

import { useId, type InputHTMLAttributes, type ReactNode } from 'react';

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label: ReactNode;
  description?: ReactNode;
};

export function Checkbox({ label, description, id, ...rest }: CheckboxProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const descriptionId = `${inputId}-description`;
  return (
    <div className="ui-checkbox">
      <input
        {...rest}
        id={inputId}
        type="checkbox"
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
