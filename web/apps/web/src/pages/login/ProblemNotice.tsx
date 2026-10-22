// web/apps/web/src/pages/login/ProblemNotice.tsx
// 로그인의 실패 한 줄. 문의할 때 알려 줄 요청 번호가 있으면 함께 보인다.

import { Notice } from '@ai-trpg/ui';
import type { LoginProblem } from '../../auth/loginProblem';

export function ProblemNotice({ problem }: { problem: LoginProblem | undefined }) {
  if (!problem) return null;
  return (
    <Notice tone="error">
      {problem.message}
      {problem.requestId ? <small className="request-id"> (요청 번호 {problem.requestId})</small> : null}
    </Notice>
  );
}
