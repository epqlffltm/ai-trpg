// web/apps/web/src/pages/trpg/AdultContentHint.tsx
// 성인용 시나리오가 왜 안 보이는지의 한 줄(화면 명세 B1 의 "비활성인 조건").
// 서버는 성인 확인이 안 된 사람에게 성인용을 없는 것으로 준다(목록에서 빠지고 total 에도 없다). 그래서 숨긴 것이 있는지 알 수 없고,
// 이 줄은 늘 같은 말이다. 성인 확인을 한 사람(adult_content)에게는 보이지 않는다. 본인인증 전이면 본인인증(A3)으로 가는 길을 붙인다.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { meQuery } from '../../auth/queries';
import { useSession } from '../../auth/useSession';

export function AdultContentHint() {
  const session = useSession();
  if (!session) return <p className="hint">성인용 시나리오는 로그인하고 성인 확인을 하면 보입니다.</p>;
  return <SignedInHint />;
}

function SignedInHint() {
  const me = useQuery(meQuery());
  if (!me.data || me.data.identity.adult_content) return null;
  return (
    <p className="hint">
      성인용 시나리오는 본인인증으로 성인 확인을 하면 보입니다. {me.data.identity.verified ? null : <Link to="/me/identity">본인인증하기</Link>}
    </p>
  );
}
