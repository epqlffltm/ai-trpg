// web/apps/web/src/pages/identity/IdentityPage.tsx
// 본인인증(A3, /me/identity). 휴대폰 본인인증으로 나이를 확인하고 환영 실버를 한 번 받는다. 로그인해야 열린다(RequireSession).
// 인증 전이면 무엇이 열리는지와 업체의 창(지금은 시험용 창, identityProvider.ts), 인증 뒤면 상태와 지갑·출석으로 가는 길.
// 결과의 처리(토큰 갱신, 만 14세 미만의 로그아웃)는 useVerifyIdentity 가 맡는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { identityLabel } from '../me/accountLabels';
import { FakeIdentityForm } from './FakeIdentityForm';
import { koreanToday, providerKind } from './identityProvider';
import { useVerifyIdentity } from './useVerifyIdentity';

export function IdentityPage() {
  const me = useQuery(meQuery());
  return (
    <main className="page page--medium">
      <p>
        <Link to="/me">내 정보</Link>
      </p>
      <h1>본인인증</h1>
      {me.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {me.isError ? (
        <Notice tone="error">
          계정을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void me.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {me.data ? me.data.identity.verified ? <Verified me={me.data} /> : <Unverified me={me.data} /> : null}
    </main>
  );
}

function Verified({ me }: { me: Me }) {
  const { identity } = me;
  return (
    <section className="page-section" aria-labelledby="identity-done-heading">
      <h2 id="identity-done-heading">본인인증을 마쳤습니다</h2>
      <p>상태: {identityLabel(identity)}</p>
      {identity.legal_adult ? null : <p className="hint">미성년자는 보호자가 동의해야 충전할 수 있습니다. 보호자 동의 화면은 준비 중입니다.</p>}
      {identity.adult_content ? null : <p className="hint">성인용 내용은 만 19세가 되는 해의 1월 1일부터 열립니다. 그날이 지나면 다시 인증하지 않아도 저절로 열립니다.</p>}
      <p>
        환영 실버는 <Link to="/wallet">지갑</Link>에서 확인합니다(조금 늦게 들어올 수 있습니다). 이제 <Link to="/wallet/attendance">출석</Link>할 수 있습니다.
      </p>
    </section>
  );
}

function Unverified({ me }: { me: Me }) {
  const verifying = useVerifyIdentity();
  const kind = providerKind();
  return (
    <section className="page-section" aria-labelledby="identity-start-heading">
      <h2 id="identity-start-heading">휴대폰 본인인증</h2>
      <p>본인인증을 하면 이것들이 열립니다.</p>
      <ul>
        <li>환영 실버(한 번)와 매일의 출석 보상</li>
        <li>충전(미성년자는 보호자의 동의 뒤에)</li>
        <li>성인 확인: 만 19세가 되는 해부터 성인용 시나리오</li>
      </ul>
      <p className="hint">한 사람은 한 계정만 인증합니다. 만 14세 미만은 이용할 수 없습니다. 이름이나 전화번호는 받지 않습니다. 나이를 가르는 데 생일을, 한 사람 한 계정을 지키는 데 업체가 주는 식별값을 씁니다.</p>
      {verifying.problem ? <Notice tone="error">{verifying.problem}</Notice> : null}
      {kind === 'fake' ? (
        <FakeIdentityForm publicId={me.public_id} today={koreanToday()} busy={verifying.busy} onToken={(token) => void verifying.verify(token)} />
      ) : (
        <Notice>지금은 본인인증을 할 수 없습니다. 본인확인 업체를 준비하고 있습니다.</Notice>
      )}
    </section>
  );
}
