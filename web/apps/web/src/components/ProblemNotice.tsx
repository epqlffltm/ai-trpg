// web/apps/web/src/components/ProblemNotice.tsx
// 인증 화면(로그인, 가입, 비밀번호)의 실패 한 줄. 문의할 때 알려 줄 요청 번호가 있으면 함께 보인다.
// reveal 을 주면 실패가 바뀔 때마다 틀린 첫 칸이나 이 줄을 눈앞에 데려온다(revealProblem). 보내기 버튼이 있는 폼에만 준다.
// 방 안의 버튼처럼 자리를 옮기면 안 되는 곳에는 주지 않는다(기본은 그대로 보이기만 한다).

import { Notice } from '@ai-trpg/ui';
import { useEffect, useRef } from 'react';
import type { FormProblem } from '../auth/problem';
import { revealProblem } from './revealProblem';

type Props = { problem: FormProblem | undefined; reveal?: boolean };

export function ProblemNotice({ problem, reveal = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (reveal && problem && ref.current) revealProblem(ref.current);
  }, [problem, reveal]);

  if (!problem) return null;
  const notice = (
    <Notice tone="error">
      {problem.message}
      {problem.requestId ? <small className="request-id"> (요청 번호 {problem.requestId})</small> : null}
    </Notice>
  );
  if (!reveal) return notice;
  // 초점을 받을 수 있게 감싼다. 탭으로는 들르지 않는다(tabIndex -1). 누른 뒤 코드가 옮긴 초점은 브라우저가 테두리를 그리지 않는다(:focus-visible)
  return (
    <div ref={ref} className="problem-notice" tabIndex={-1}>
      {notice}
    </div>
  );
}
