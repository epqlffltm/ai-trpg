// web/apps/web/src/pages/guardian/GuardianConsentPage.tsx
// 보호자 동의 메일의 링크가 여는 화면(A4, 인증 서버의 GUARDIAN_CONSENT_URL, /guardian/consent#token=). 로그인하지 않는다.
// 보호자가 휴대폰 본인인증을 하면 링크의 글자와 함께 동의를 낸다. 업체의 창은 회원의 본인인증(A3)과 같은 갈래다(identityProvider.ts).
// 메일을 모바일에서 여는 일이 많아 좁은 화면을 먼저 본다. 링크의 글자는 useLinkToken 이 읽고 주소에서 지운다.

import { Notice } from '@ai-trpg/ui';
import { FakeIdentityForm } from '../identity/FakeIdentityForm';
import { koreanToday, providerKind } from '../identity/identityProvider';
import { GUARDIAN_FAKE_DI, GUARDIAN_PRESETS } from './guardianPresets';
import { useGuardianConsent } from './useGuardianConsent';
import { useLinkToken } from './useLinkToken';

export function GuardianConsentPage() {
  const token = useLinkToken();
  return (
    <main className="page page--narrow">
      <h1>보호자 동의</h1>
      {token ? <ConsentBody token={token} /> : <Notice tone="error">링크가 올바르지 않습니다. 메일에 온 링크를 그대로 열어 주세요.</Notice>}
    </main>
  );
}

function ConsentBody({ token }: { token: string }) {
  const consenting = useGuardianConsent(token);
  if (consenting.done) {
    return (
      <section className="page-section" aria-labelledby="consent-done-heading">
        <h2 id="consent-done-heading">동의했습니다</h2>
        <p>회원이 이제 충전할 수 있습니다. 보호자와 회원에게 확인 메일을 보냈습니다.</p>
        <p className="hint">결제와 청약철회마다 메일로 알려 드립니다. 확인 메일의 철회 링크로 언제든 동의를 철회할 수 있습니다.</p>
      </section>
    );
  }
  return (
    <section className="page-section" aria-labelledby="consent-heading">
      <h2 id="consent-heading">결제(충전)에 동의하기</h2>
      <p>만 19세 미만의 회원이 AI TRPG 에서 충전하려고 보호자의 동의를 부탁했습니다.</p>
      <ul>
        <li>보호자 본인의 휴대폰으로 본인인증을 합니다. 보호자는 성년(만 19세 이상)이어야 합니다</li>
        <li>계정을 만들지 않습니다. 이름이나 전화번호는 받지 않습니다</li>
        <li>동의한 뒤에는 결제와 청약철회마다 메일로 알려 드리고, 메일의 링크로 언제든 철회할 수 있습니다</li>
      </ul>
      {consenting.problem ? <Notice tone="error">{consenting.problem.message}</Notice> : null}
      {consenting.problem?.restart ? null : <ConsentForm busy={consenting.busy} onToken={(identityToken) => void consenting.consent(identityToken)} />}
    </section>
  );
}

function ConsentForm({ busy, onToken }: { busy: boolean; onToken: (token: string) => void }) {
  if (providerKind() !== 'fake') return <Notice>지금은 본인인증을 할 수 없습니다. 본인확인 업체를 준비하고 있습니다.</Notice>;
  return (
    <FakeIdentityForm
      initialDi={GUARDIAN_FAKE_DI}
      presets={GUARDIAN_PRESETS}
      note="실제 휴대폰 인증이 아닙니다. 보호자의 생일과 사람 식별값을 골라 흐름을 봅니다. 회원 본인의 식별값을 적으면 막힙니다."
      submitLabel="이 사람으로 동의하기"
      today={koreanToday()}
      busy={busy}
      onToken={onToken}
    />
  );
}
