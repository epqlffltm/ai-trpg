// web/apps/web/src/pages/me/MyConsents.tsx
// 마이페이지의 "동의"(#450). 상태는 GET /me/consents.
//   - 필수(이용약관, 개인정보): 동의한 판과 날만 보인다. 끄는 단추가 없다. 철회는 탈퇴다(서버도 400 consent_required).
//   - 선택(마케팅, AI 학습): 켜고 끈다. 켤 때는 그 판의 문서를 보이고 창의 "동의하기"로 받는다(PUT). 끌 때는 바로 철회한다(DELETE).
// 판이 바뀌었으면(409) 상태를 다시 읽는다. 화면이 갖지 않은 판이면 켜지 못한다(옛 문서로 동의를 받지 않는다).
// 화면 명세는 설정(A12)에 두기로 했는데 A12 가 출시 뒤라서 철회할 길을 여기 둔다(2026-10-22 결정).

import { Button, Checkbox, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { agreeConsent, withdrawConsent } from '../../api/account';
import type { ConsentState } from '../../api/types';
import { describeConsentProblem, type ConsentProblem } from '../../auth/accountProblem';
import { myConsentsQuery } from '../../auth/queries';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDate } from '../../format/dateTime';
import { ConsentDocumentDialog, type ViewingDocument } from '../../legal/ConsentDocumentDialog';
import { consentDocumentName, consentItemInfo } from '../../legal/consentItems';

export function MyConsents() {
  const consents = useQuery(myConsentsQuery());
  const queryClient = useQueryClient();
  const [viewing, setViewing] = useState<ViewingDocument | null>(null);
  const [agreeing, setAgreeing] = useState<ConsentState | null>(null);
  const [busyItem, setBusyItem] = useState<string | null>(null);
  const [problem, setProblem] = useState<ConsentProblem | undefined>();
  const closeViewing = useCallback(() => setViewing(null), []);
  const closeAgreeing = useCallback(() => setAgreeing(null), []);
  const states = consents.data ?? [];

  async function change(item: string, action: () => Promise<ConsentState[]>) {
    setBusyItem(item);
    setProblem(undefined);
    try {
      queryClient.setQueryData(myConsentsQuery().queryKey, await action());
      setAgreeing(null);
    } catch (error) {
      const next = describeConsentProblem(error);
      setProblem(next);
      if (next.consentsChanged) {
        setAgreeing(null);
        await consents.refetch();
      }
    }
    setBusyItem(null);
  }

  function toggle(state: ConsentState, on: boolean) {
    if (on) setAgreeing(state);
    else void change(state.item, () => withdrawConsent(state.item));
  }

  return (
    <section className="page-section" aria-labelledby="consents-heading">
      <h2 id="consents-heading">동의</h2>
      {consents.isPending ? <p>불러오는 중</p> : null}
      {consents.isError ? (
        <Notice tone="error">
          동의를 불러오지 못했습니다. <Button variant="quiet" onClick={() => void consents.refetch()}>다시 시도</Button>
        </Notice>
      ) : null}
      {agreeing ? null : <ProblemNotice problem={problem} />}
      {states.filter((state) => state.required).map((state) => (
        <RequiredRow key={state.item} state={state} onView={setViewing} />
      ))}
      {states.some((state) => !state.required) ? (
        <p className="consents__group">선택 항목은 언제든 켜고 끌 수 있습니다. 필수 항목을 철회하려면 탈퇴해야 합니다.</p>
      ) : null}
      {states.filter((state) => !state.required).map((state) => (
        <OptionalRow
          key={state.item}
          state={state}
          busy={busyItem === state.item}
          onToggle={(on) => toggle(state, on)}
          onView={setViewing}
        />
      ))}
      <ConsentDocumentDialog viewing={viewing} onClose={closeViewing} />
      <ConsentDocumentDialog
        viewing={agreeing ? documentOf(agreeing) : null}
        onClose={closeAgreeing}
        footer={
          agreeing ? (
            <>
              <ProblemNotice problem={problem} />
              <Button
                busy={busyItem === agreeing.item}
                onClick={() => void change(agreeing.item, () => agreeConsent(agreeing.item, agreeing.version))}
              >
                동의하기
              </Button>
            </>
          ) : null
        }
      />
    </section>
  );
}

/** 그 항목의 지금 판의 문서. 화면이 갖지 않은 판이면 null */
function documentOf(state: ConsentState): ViewingDocument | null {
  const name = consentDocumentName(state.item, state.version);
  return name ? { label: consentItemInfo(state.item).label, name } : null;
}

/** "1판에 동의(2026년 10월 20일)" 꼴. 동의하지 않았으면 "동의하지 않음" */
function agreedText(state: ConsentState): string {
  if (state.agreed_version === null || state.agreed_at === null) return '동의하지 않음';
  return `${state.agreed_version}판에 동의(${formatDate(state.agreed_at)})`;
}

type RowProps = { state: ConsentState; onView: (document: ViewingDocument) => void };

function RequiredRow({ state, onView }: RowProps) {
  const info = consentItemInfo(state.item);
  const document = documentOf(state);
  return (
    <div className="consent-row">
      <div>
        <p className="consent-row__label">[필수] {info.label}</p>
        <p className="consent-row__description">
          {info.summary} · {agreedText(state)}
        </p>
      </div>
      {document ? (
        <Button variant="quiet" onClick={() => onView(document)}>
          보기
        </Button>
      ) : null}
    </div>
  );
}

type OptionalRowProps = RowProps & { busy: boolean; onToggle: (on: boolean) => void };

function OptionalRow({ state, busy, onToggle, onView }: OptionalRowProps) {
  const info = consentItemInfo(state.item);
  const document = documentOf(state);
  const agreed = state.agreed_version !== null;
  const older = agreed && state.agreed_version !== state.version ? ` · 지금은 ${state.version}판` : '';
  return (
    <div className="consent-row">
      <Checkbox
        label={`[선택] ${info.label}`}
        description={`${info.summary} · ${agreedText(state)}${older}`}
        checked={agreed}
        disabled={busy || (!agreed && document === null)}
        aria-busy={busy || undefined}
        onChange={(event) => onToggle(event.target.checked)}
      />
      {document ? (
        <Button variant="quiet" onClick={() => onView(document)}>
          보기
        </Button>
      ) : null}
    </div>
  );
}
