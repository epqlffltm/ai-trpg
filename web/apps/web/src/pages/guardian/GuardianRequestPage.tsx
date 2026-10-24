// web/apps/web/src/pages/guardian/GuardianRequestPage.tsx
// 보호자 동의(A4, /me/guardian). 미성년자(성년 전)가 보호자에게 결제(충전) 동의를 부탁한다. 로그인해야 열린다(RequireSession).
// 단계(guardianView.ts)마다: 본인인증 전이면 A3 으로, 성년이면 필요 없음, 동의 전·요청함·철회됨이면 보호자 이메일의 창,
// 보호자가 동의했으면 철회는 보호자의 메일 링크로만 한다는 안내. 보내기와 실패의 처리는 useGuardianRequest 가 맡는다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { canRequest, guardianEmailHint, guardianStage, type GuardianStage } from './guardianView';
import { useGuardianRequest } from './useGuardianRequest';

export function GuardianRequestPage() {
  const me = useQuery(meQuery());
  return (
    <main className="page page--medium">
      <p>
        <Link to="/me">내 정보</Link>
      </p>
      <h1>보호자 동의</h1>
      {me.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {me.isError ? (
        <Notice tone="error">
          계정을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void me.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {me.data ? <GuardianBody me={me.data} /> : null}
    </main>
  );
}

function GuardianBody({ me }: { me: Me }) {
  const stage = guardianStage(me);
  return (
    <section className="page-section" aria-labelledby="guardian-heading">
      <h2 id="guardian-heading">결제(충전)에 보호자의 동의</h2>
      <p className="hint">만 19세 생일 전에는 보호자가 동의해야 충전할 수 있습니다. 보호자는 계정을 만들지 않고, 메일의 링크에서 휴대폰 본인인증을 하고 동의합니다. 동의한 뒤에는 결제마다 보호자에게 메일이 갑니다.</p>
      <StageNotice stage={stage} />
      {canRequest(stage) ? <RequestForm myEmail={me.email} again={stage === 'requested'} /> : null}
    </section>
  );
}

function StageNotice({ stage }: { stage: GuardianStage }) {
  switch (stage) {
    case 'unverified':
      return (
        <Notice>
          나이를 알아야 해서 본인인증을 먼저 합니다. <Link to="/me/identity">본인인증하기</Link>
        </Notice>
      );
    case 'adult':
      return <Notice>성년이라 보호자의 동의가 필요 없습니다. 바로 충전할 수 있습니다.</Notice>;
    case 'consented':
      return (
        <Notice>
          보호자가 동의했습니다. <Link to="/wallet/charge">충전</Link>할 수 있습니다. 동의의 철회는 보호자가 받은 메일의 링크로만 합니다. 보호자를 바꾸려면 지금의 보호자가 먼저 철회해야 합니다.
        </Notice>
      );
    case 'requested':
      return <Notice>보호자의 동의를 기다리는 중입니다. 링크는 7일 동안 쓸 수 있습니다. 메일이 오지 않았으면 다시 보낼 수 있습니다(앞서 보낸 링크는 쓸 수 없게 됩니다).</Notice>;
    case 'revoked':
      return <Notice>보호자가 동의를 철회해 충전할 수 없습니다. 다시 부탁할 수 있습니다.</Notice>;
    default:
      return null;
  }
}

function RequestForm({ myEmail, again }: { myEmail: string; again: boolean }) {
  const [email, setEmail] = useState('');
  const [tried, setTried] = useState('');
  const sending = useGuardianRequest();
  const hint = guardianEmailHint(email, myEmail);
  const blocked = email.trim() === '' || hint !== null;
  // 서버가 칸에 단 글은 그 주소를 그대로 둘 때만 보인다
  const serverHint = email.trim() === tried ? sending.problem?.email : undefined;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    setTried(email.trim());
    await sending.request(email.trim());
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="보호자에게 부탁하기">
      {sending.sentTo ? <Notice>{sending.sentTo} 로 동의 요청 메일을 보냈습니다.</Notice> : null}
      {sending.problem && !sending.problem.email ? <Notice tone="error">{sending.problem.message}</Notice> : null}
      <TextField
        label="보호자의 이메일"
        type="email"
        autoComplete="off"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={hint ?? serverHint}
      />
      <p className="hint">보호자에게는 내 닉네임만 보입니다. 아이디와 내 이메일은 보이지 않습니다.</p>
      <div className="form-actions">
        <Button type="submit" busy={sending.busy} disabled={blocked}>
          {again ? '다시 보내기' : '동의 요청 보내기'}
        </Button>
      </div>
    </form>
  );
}
