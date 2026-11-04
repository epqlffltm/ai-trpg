// web/apps/web/src/pages/wallet/CardReturnPage.tsx
// 토스페이먼츠의 카드 등록 창이 돌아오는 화면(#980, /wallet/card/return). 로그인해야 열린다(App.tsx 의 RequireSession).
// 성공으로 돌아왔으면 카드를 등록하고 결과를 보인다. 실패로 돌아왔으면 까닭을 보인다. 어느 쪽이든 지갑으로 돌아간다.
// 주소를 읽지 못했으면 서버에 아무것도 보내지 않는다(tossCard.ts 의 readCardReturn).

import { Notice } from '@ai-trpg/ui';
import { Link, useSearchParams } from 'react-router';
import { formatDateTime } from '../../format/dateTime';
import { ProblemNotice } from './ProblemNotice';
import { cardReturnFailureText, readCardReturn } from './tossCard';
import { useCardReturn } from './useCardReturn';

export function CardReturnPage() {
  const [search] = useSearchParams();
  const result = readCardReturn(search);
  return (
    <main className="page page--medium">
      <h1>카드 등록</h1>
      {result.kind === 'registered' ? (
        <Registering authKey={result.authKey} customerKey={result.customerKey} />
      ) : (
        <Notice tone="error">
          {result.kind === 'failed' ? cardReturnFailureText(result.code) : '카드 등록 창의 결과를 읽지 못했습니다. 다시 해 주세요.'}
        </Notice>
      )}
      <p>
        <Link to="/wallet">지갑으로</Link>
      </p>
    </main>
  );
}

/** 인증 키로 카드를 등록하고 결과를 보인다 */
function Registering({ authKey, customerKey }: { authKey: string; customerKey: string }) {
  const { card, busy, problem } = useCardReturn(authKey, customerKey);
  if (busy) return <p aria-busy="true">카드를 등록하는 중입니다.</p>;
  if (problem) return <ProblemNotice problem={problem} />;
  if (!card) return null;
  return (
    <Notice>
      카드를 등록했습니다: {card.number} · {formatDateTime(card.registered_at)}. 지갑에서 자동 충전을 켤 수 있습니다.
    </Notice>
  );
}
