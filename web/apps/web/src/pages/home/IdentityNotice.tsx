// web/apps/web/src/pages/home/IdentityNotice.tsx
// 홈(A1)의 본인인증 안내. 로그인했고 본인인증 전이면 한 줄과 본인인증(A3)으로 가는 길을 보인다.
// 내 정보를 읽지 못했거나 읽는 중이면 아무것도 보이지 않는다(홈을 막지 않는다). 인증하면 내 정보가 바뀌어 사라진다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';

export function IdentityNotice() {
  const me = useQuery(meQuery());
  // 다른 서버의 시험용 답처럼 identity 가 빠진 내 정보도 홈을 깨뜨리지 않게 본다
  const identity = me.data?.identity as Me['identity'] | undefined;
  if (!identity || identity.verified) return null;
  return (
    <Notice>
      본인인증을 하면 환영 실버와 매일의 출석 보상을 받습니다. <Link to="/me/identity">본인인증하기</Link>
    </Notice>
  );
}
