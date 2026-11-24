// web/apps/web/src/components/ReferencesToggle.tsx
// 대화(C3)와 세션(D2)의 "참고 자료 쓰기" 켜기(#1338). 왼쪽 열의 페르소나·모델 창에 둔다.
// 참고 자료는 미리 넣어 둔 바깥 자료(D&D SRD 5.1, 위키백과)다. 켜면 다음 말부터 답에 섞인다. 값을 더 받지 않는다.
// 제작자가 허용한 캐릭터·세계관에서만 보인다(allowed). 허용하지 않았으면 켤 수 없어 단추도 없다.
// 바꾸는 중이나 답을 받는 중에는 막는다. 실패하면 까닭을 아래에 적는다(describeReferencesProblem).

import { Checkbox, Notice } from '@ai-trpg/ui';
import { useId } from 'react';
import { ApiError, NetworkError } from '../api/errors';

type Props = {
  /** 캐릭터·세계관의 판이 허용하는가(제작자) */
  allowed: boolean;
  /** 이 대화·세션에서 켰는가(사람) */
  enabled: boolean;
  disabled: boolean;
  error: unknown;
  onChange: (enabled: boolean) => void;
};

/** 켜기를 바꾸지 못한 까닭. 순수한 함수다 */
export function describeReferencesProblem(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error instanceof ApiError && error.code === 'references_not_allowed') return '만든 사람이 참고 자료를 허용하지 않았습니다.';
  if (error instanceof ApiError && error.code === 'too_many_attempts') return `너무 자주 바꿨습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 해 주세요.`;
  return '참고 자료를 바꾸지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}

export function ReferencesToggle({ allowed, enabled, disabled, error, onChange }: Props) {
  const id = useId();
  if (!allowed) return null;
  return (
    <div className="references-toggle">
      <Checkbox
        id={id}
        label="참고 자료 쓰기"
        description="바깥 자료(D&D SRD, 위키백과)에서 지금의 이야기에 맞는 것을 골라 답에 섞습니다. 만든 사람의 설정이 먼저입니다. 값은 더 들지 않습니다."
        checked={enabled}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      {error ? <Notice tone="error">{describeReferencesProblem(error)}</Notice> : null}
    </div>
  );
}
