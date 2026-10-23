// web/apps/web/src/pages/trpg/studio/scenarios/ScenarioForm.tsx
// 시나리오의 탭 하나의 폼 틀(B9). 위에 실패, 아래에 저장 단추와 "저장했습니다."를 둔다. 칸과 보내기는 탭이 맡는다.

import { Button } from '@ai-trpg/ui';
import type { FormEvent, ReactNode } from 'react';
import type { FormProblem } from '../../../../auth/problem';
import { ProblemNotice } from '../../../../components/ProblemNotice';

type Props = {
  /** 폼의 이름(탭의 이름) */
  label: string;
  busy: boolean;
  problem: FormProblem | undefined;
  saved: boolean;
  /** 칸에 고칠 것이 있어 보내지 않는다 */
  blocked: boolean;
  onSubmit: () => void;
  children: ReactNode;
  /** 저장 옆의 단추(지우기 같은 것) */
  actions?: ReactNode;
};

export function ScenarioForm({ label, busy, problem, saved, blocked, onSubmit, children, actions }: Props) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!blocked) onSubmit();
  }

  return (
    <form onSubmit={submit} noValidate aria-label={label}>
      <ProblemNotice problem={problem} />
      {children}
      <div className="form-actions">
        <Button type="submit" busy={busy} disabled={blocked}>
          저장
        </Button>
        {actions}
        {saved ? (
          <span className="hint" role="status">
            저장했습니다.
          </span>
        ) : null}
      </div>
    </form>
  );
}
