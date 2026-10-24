// web/apps/web/src/pages/guardian/GuardianRevokePage.tsx
// 보호자 동의를 철회하는 링크가 여는 화면(A4, 인증 서버의 GUARDIAN_REVOKE_URL, /guardian/revoke#token=). 로그인하지 않는다.
// 링크를 여는 것만으로 철회하지 않는다(메일 앱이 미리 열어 보는 일이 있다). 무엇이 달라지는지 적고 단추로 낸다.
// 두 번 내도 서버는 200 이다. 이번에 철회했는지(revoked)에 따라 글이 다르다.

import { Button, Notice } from '@ai-trpg/ui';
import { useGuardianRevoke } from './useGuardianRevoke';
import { useLinkToken } from './useLinkToken';

export function GuardianRevokePage() {
  const token = useLinkToken();
  return (
    <main className="page page--narrow">
      <h1>보호자 동의 철회</h1>
      {token ? <RevokeBody token={token} /> : <Notice tone="error">링크가 올바르지 않습니다. 메일에 온 링크를 그대로 열어 주세요.</Notice>}
    </main>
  );
}

function RevokeBody({ token }: { token: string }) {
  const revoking = useGuardianRevoke(token);
  if (revoking.revoked !== null) {
    return (
      <section className="page-section" aria-labelledby="revoke-done-heading">
        <h2 id="revoke-done-heading">{revoking.revoked ? '동의를 철회했습니다' : '이미 철회한 동의입니다'}</h2>
        <p>회원은 이제 충전할 수 없습니다. 회원이 다시 부탁하면 새 메일이 갑니다.</p>
      </section>
    );
  }
  return (
    <section className="page-section" aria-labelledby="revoke-heading">
      <h2 id="revoke-heading">결제(충전)의 동의를 거두기</h2>
      <p>철회하면 회원은 더 충전할 수 없습니다. 철회는 앞으로의 충전만 막고, 이미 한 결제는 이 화면에서 바뀌지 않습니다.</p>
      {revoking.problem ? <Notice tone="error">{revoking.problem.message}</Notice> : null}
      {revoking.problem?.restart ? null : (
        <div className="form-actions">
          <Button busy={revoking.busy} onClick={() => void revoking.revoke()}>
            동의 철회하기
          </Button>
        </div>
      )}
    </section>
  );
}
