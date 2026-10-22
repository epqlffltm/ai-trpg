// web/apps/web/src/components/ProblemNotice.tsx
// 인증 화면(로그인, 가입, 비밀번호)의 실패 한 줄. 문의할 때 알려 줄 요청 번호가 있으면 함께 보인다.

import { Notice } from '@ai-trpg/ui';
import type { FormProblem } from '../auth/problem';

export function ProblemNotice({ problem }: { problem: FormProblem | undefined }) {
  if (!problem) return null;
  return (
    <Notice tone="error">
      {problem.message}
      {problem.requestId ? <small className="request-id"> (요청 번호 {problem.requestId})</small> : null}
    </Notice>
  );
}
