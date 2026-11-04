// web/apps/web/src/pages/wallet/AutoChargeForm.tsx
// 자동 충전(#980)의 설정. 켜기, 기준 골드, 살 상품, 한 달 상한(원). 적으면 서버가 돌려준 설정을 보인다.
// 값은 화면이 먼저 보고(autoChargeView 의 toSettings) 서버가 다시 본다. 켜려면 카드가 있고 지금 결제할 수 있어야 한다(서버가 본다).
//
// 켜는 설정을 적을 때마다 자동 결제에 동의한다(가입 때가 아니라 켤 때, 2026-11-04 결정).
// 동의하는 칸 바로 위에 고른 조건을 글로 보이고(agreementLines), 동의 문서의 그 판을 창으로 볼 수 있다.
// 동의하는 칸은 미리 체크하지 않는다. 서버가 판과 조건과 시각을 적는다. 판이 바뀌었으면 서버가 409 로 알린다.

import { Button, Checkbox, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { AutoChargeSettings } from '../../api/autoCharge';
import type { AutoCharge, Product } from '../../api/types';
import { autoChargeDocumentName } from '../../legal/autoChargeTerms';
import { ConsentDocumentDialog, type ViewingDocument } from '../../legal/ConsentDocumentDialog';
import { wonLabel } from '../charge/chargeView';
import { agreementLines, initialDraft, toSettings, type AutoChargeDraft } from './autoChargeView';

type Props = {
  current: AutoCharge;
  products: Product[];
  busy: boolean;
  onSave: (settings: AutoChargeSettings) => void;
};

export function AutoChargeForm({ current, products, busy, onSave }: Props) {
  const [draft, setDraft] = useState<AutoChargeDraft>(() => initialDraft(current, products));
  const [problem, setProblem] = useState<string | null>(null);
  const [viewing, setViewing] = useState<ViewingDocument | null>(null);
  const documentName = autoChargeDocumentName(current.terms.version);

  function change(patch: Partial<AutoChargeDraft>) {
    // 조건이 바뀌면 그 조건에 다시 동의한다
    setDraft((before) => ({ ...before, ...patch, agreed: 'agreed' in patch ? Boolean(patch.agreed) : false }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.enabled && documentName === null) {
      setProblem('화면이 새 자동 결제 동의를 아직 갖지 않았습니다. 페이지를 새로 고친 뒤 다시 해 주세요.');
      return;
    }
    const checked = toSettings(draft, products, current.terms.version);
    setProblem(checked.problem);
    if (checked.settings) onSave(checked.settings);
  }

  return (
    <form onSubmit={submit} aria-label="자동 충전 설정" noValidate>
      <Checkbox
        label="자동 충전 켜기"
        description="골드가 기준 아래로 떨어지면 등록한 카드로 고른 상품을 한 번 삽니다. 세 번 이어서 실패하면 꺼집니다."
        checked={draft.enabled}
        onChange={(event) => change({ enabled: event.target.checked })}
      />
      <TextField
        label="기준 골드"
        inputMode="numeric"
        value={draft.threshold}
        onChange={(event) => change({ threshold: event.target.value })}
      />
      <SelectField label="살 상품" value={draft.productId} onChange={(event) => change({ productId: event.target.value })}>
        {products.map((product) => (
          <option key={product.id} value={product.id}>
            {product.name} · {wonLabel(product.price)}
          </option>
        ))}
      </SelectField>
      <TextField
        label="한 달 상한(원)"
        inputMode="numeric"
        value={draft.monthlyLimit}
        onChange={(event) => change({ monthlyLimit: event.target.value })}
      />
      <p className="hint">한 달(한국 날짜)에 자동으로 결제하는 돈의 합이 이 값을 넘지 않습니다.</p>
      {draft.enabled ? (
        <Agreement
          current={current}
          draft={draft}
          products={products}
          documentName={documentName}
          onView={setViewing}
          onAgree={(agreed) => change({ agreed })}
        />
      ) : null}
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      {current.consecutive_failures > 0 ? <p className="hint">이어서 실패한 자동 결제: {current.consecutive_failures}번</p> : null}
      <Button type="submit" busy={busy}>
        저장
      </Button>
      <ConsentDocumentDialog viewing={viewing} onClose={() => setViewing(null)} />
    </form>
  );
}

type AgreementProps = {
  current: AutoCharge;
  draft: AutoChargeDraft;
  products: Product[];
  documentName: string | null;
  onView: (document: ViewingDocument) => void;
  onAgree: (agreed: boolean) => void;
};

/** 자동 결제 동의. 고른 조건, 동의 문서 보기, 동의하는 칸 */
function Agreement({ current, draft, products, documentName, onView, onAgree }: AgreementProps) {
  const lines = agreementLines(draft, products);
  const { version, agreed_version: agreedVersion } = current.terms;
  return (
    <section className="auto-charge__agreement" aria-label="자동 결제 동의">
      {agreedVersion !== null && agreedVersion !== version ? (
        <Notice>자동 결제 동의의 내용이 바뀌었습니다. 바뀐 내용을 읽고 다시 동의해 주세요.</Notice>
      ) : null}
      {lines ? (
        <ul>
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="hint">기준 골드, 상품, 한 달 상한을 맞게 적으면 동의할 조건이 보입니다.</p>
      )}
      {documentName ? (
        <Button variant="quiet" onClick={() => onView({ label: '자동 충전 이용 동의', name: documentName })}>
          동의 내용 보기
        </Button>
      ) : null}
      <Checkbox
        label="위 조건과 자동 충전 이용 동의에 따라 자동 결제하는 것에 동의합니다"
        checked={draft.agreed}
        disabled={lines === null || documentName === null}
        onChange={(event) => onAgree(event.target.checked)}
      />
    </section>
  );
}
