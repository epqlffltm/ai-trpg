// web/apps/web/src/pages/wallet/ProblemNotice.tsx
// 자동 충전(#980)이 되지 않은 까닭 한 줄. 갈 곳(본인인증, 보호자 동의)이 있으면 그 길을 붙인다.

import { Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { AutoChargeProblem } from './autoChargeProblem';

export function ProblemNotice({ problem }: { problem: AutoChargeProblem }) {
  return (
    <Notice tone="error">
      {problem.message}
      {problem.link ? (
        <>
          {' '}
          <Link to={problem.link.to}>{problem.link.label}</Link>
        </>
      ) : null}
    </Notice>
  );
}
