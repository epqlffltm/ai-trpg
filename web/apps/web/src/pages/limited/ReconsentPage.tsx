// web/apps/web/src/pages/limited/ReconsentPage.tsx
// 다시 동의(#450). 필수 문서의 판이 올라 동의가 남았으면 어느 화면으로 와도 이것만 보인다(LimitedSessionGate).
//
// 받을 항목과 판은 GET /me/consents 의 pending 이다. 항목마다 새 판의 문서를 볼 수 있고, 미리 체크하지 않는다.
// 다 체크하고 누르면 항목마다 PUT /me/consents/{item} 을 보내고 /refresh 로 모든 서버에 통하는 토큰을 받는다.
// 그러면 상태가 바뀌어 원래 화면이 그 자리에 뜬다. 다른 화면으로 보내지 않는다(화면 명세의 A2).
// 판이 또 바뀌었으면(409) 다시 읽고 체크를 비운다. 화면이 갖지 않은 판이면 받지 않는다(옛 문서로 동의를 받지 않는다).

import { Button, Checkbox, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useState, type FormEvent } from 'react';
import { agreeConsent } from '../../api/account';
import { refreshSession } from '../../api/refresh';
import type { ConsentState } from '../../api/types';
import { describeConsentProblem, type ConsentProblem } from '../../auth/accountProblem';
import { myConsentsQuery } from '../../auth/queries';
import { ProblemNotice } from '../../components/ProblemNotice';
import { ConsentDocumentDialog, type ViewingDocument } from '../../legal/ConsentDocumentDialog';
import { consentDocumentName, consentItemInfo, itemsWithoutDocument } from '../../legal/consentItems';
import { allChecked, pendingItems } from './reconsent';

export function ReconsentPage() {
  const consents = useQuery(myConsentsQuery());
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [viewing, setViewing] = useState<ViewingDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ConsentProblem | undefined>();
  const close = useCallback(() => setViewing(null), []);
  const items = pendingItems(consents.data ?? []);
  const missingDocuments = itemsWithoutDocument(items);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await agreeAll(items);
      await refreshSession();
    } catch (error) {
      await fail(error);
    }
    setBusy(false);
  }

  async function fail(error: unknown) {
    const next = describeConsentProblem(error);
    setProblem(next);
    if (next.consentsChanged) {
      setChecked({});
      await consents.refetch();
    }
  }

  return (
    <main className="page page--medium">
      <h1>바뀐 약관에 동의해 주세요</h1>
      <p>아래 문서의 새 판이 시행됩니다. 동의해야 서비스를 계속 쓸 수 있습니다. 동의하지 않으려면 로그아웃하세요.</p>
      {consents.isPending ? <p>불러오는 중</p> : null}
      {consents.isError ? (
        <Notice tone="error">
          동의할 항목을 불러오지 못했습니다. <Button variant="quiet" onClick={() => void consents.refetch()}>다시 시도</Button>
        </Notice>
      ) : null}
      {missingDocuments.length > 0 ? (
        <Notice tone="error">화면에 새 판의 문서가 아직 없습니다. 새로 고친 뒤에 다시 시도해 주세요.</Notice>
      ) : null}
      {consents.isSuccess && items.length === 0 ? <NothingLeft /> : null}
      {items.length > 0 ? (
        <form onSubmit={submit} noValidate>
          <ProblemNotice problem={problem} />
          <fieldset className="consents">
            <legend>다시 동의할 항목</legend>
            {items.map((state) => (
              <PendingRow
                key={state.item}
                state={state}
                checked={Boolean(checked[state.item])}
                onChange={(value) => setChecked((current) => ({ ...current, [state.item]: value }))}
                onView={setViewing}
              />
            ))}
          </fieldset>
          <Button type="submit" busy={busy} disabled={!allChecked(items, checked) || missingDocuments.length > 0}>
            동의하고 계속하기
          </Button>
        </form>
      ) : null}
      <ConsentDocumentDialog viewing={viewing} onClose={close} />
    </main>
  );
}

/** 항목마다 차례로 받는다. 하나가 실패하면 멈춘다(받은 것은 서버에 남고, 다시 누르면 남은 것만 pending 이다) */
async function agreeAll(items: ConsentState[]): Promise<void> {
  for (const state of items) {
    await agreeConsent(state.item, state.version);
  }
}

type RowProps = {
  state: ConsentState;
  checked: boolean;
  onChange: (checked: boolean) => void;
  onView: (document: ViewingDocument) => void;
};

function PendingRow({ state, checked, onChange, onView }: RowProps) {
  const info = consentItemInfo(state.item);
  const name = consentDocumentName(state.item, state.version);
  const before = state.agreed_version ? `, 지금은 ${state.agreed_version}판에 동의함` : '';
  return (
    <div className="consent-row">
      <Checkbox
        label={`[필수] ${info.label}`}
        description={`${info.summary} (새 ${state.version}판${before})`}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {name ? (
        <Button variant="quiet" onClick={() => onView({ label: info.label, name })}>
          보기
        </Button>
      ) : null}
    </div>
  );
}

/** 서버의 상태에 남은 항목이 없다(다른 창에서 이미 동의함). 새 토큰만 받으면 된다 */
function NothingLeft() {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ConsentProblem | undefined>();

  async function proceed() {
    setBusy(true);
    setProblem(undefined);
    try {
      await refreshSession();
    } catch (error) {
      setProblem(describeConsentProblem(error));
    }
    setBusy(false);
  }

  return (
    <>
      <ProblemNotice problem={problem} />
      <Notice>동의할 항목이 남지 않았습니다.</Notice>
      <Button busy={busy} onClick={proceed}>
        계속하기
      </Button>
    </>
  );
}
