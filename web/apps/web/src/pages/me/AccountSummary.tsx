// web/apps/web/src/pages/me/AccountSummary.tsx
// 마이페이지의 "계정". GET /me 를 그대로 보인다. 닉네임과 이메일 바꾸기는 서버에 없다.
// 본인인증(A3)과 보호자 동의(A4)는 상태와 그 화면으로 가는 길을 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { meQuery } from '../../auth/queries';
import { guardianLabel, guardianLinkLabel, identityLabel, showsGuardian } from './accountLabels';

export function AccountSummary() {
  const me = useQuery(meQuery());
  return (
    <section className="page-section" aria-labelledby="account-heading">
      <h2 id="account-heading">계정</h2>
      {me.isPending ? <p>불러오는 중</p> : null}
      {me.isError ? (
        <Notice tone="error">
          계정을 불러오지 못했습니다. <Button variant="quiet" onClick={() => void me.refetch()}>다시 시도</Button>
        </Notice>
      ) : null}
      {me.data ? (
        <dl className="facts">
          <dt>닉네임</dt>
          <dd>{me.data.nickname}</dd>
          <dt>아이디</dt>
          <dd>{me.data.username}</dd>
          <dt>이메일</dt>
          <dd>{me.data.email}</dd>
          <dt>본인인증</dt>
          <dd>
            {identityLabel(me.data.identity)} <Link to="/me/identity">{me.data.identity.verified ? '자세히' : '본인인증하기'}</Link>
          </dd>
          {showsGuardian(me.data) ? (
            <>
              <dt>보호자 동의</dt>
              <dd>
                {guardianLabel(me.data.guardian_consent)} <Link to="/me/guardian">{guardianLinkLabel(me.data.guardian_consent)}</Link>
              </dd>
            </>
          ) : null}
          <dt>내 ID</dt>
          <dd>
            <code>{me.data.public_id}</code>
          </dd>
        </dl>
      ) : null}
    </section>
  );
}
