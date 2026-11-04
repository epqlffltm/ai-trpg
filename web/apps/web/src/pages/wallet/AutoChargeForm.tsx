// web/apps/web/src/pages/wallet/AutoChargeForm.tsx
// 자동 충전(#980)의 설정. 켜기, 기준 골드, 살 상품, 한 달 상한(원). 적으면 서버가 돌려준 설정을 보인다.
// 값은 화면이 먼저 보고(autoChargeView 의 toSettings) 서버가 다시 본다. 켜려면 카드가 있고 지금 결제할 수 있어야 한다(서버가 본다).

import { Button, Checkbox, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { AutoChargeSettings } from '../../api/autoCharge';
import type { AutoCharge, Product } from '../../api/types';
import { wonLabel } from '../charge/chargeView';
import { initialDraft, toSettings, type AutoChargeDraft } from './autoChargeView';

type Props = {
  current: AutoCharge;
  products: Product[];
  busy: boolean;
  onSave: (settings: AutoChargeSettings) => void;
};

export function AutoChargeForm({ current, products, busy, onSave }: Props) {
  const [draft, setDraft] = useState<AutoChargeDraft>(() => initialDraft(current, products));
  const [problem, setProblem] = useState<string | null>(null);

  function change(patch: Partial<AutoChargeDraft>) {
    setDraft((before) => ({ ...before, ...patch }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = toSettings(draft, products);
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
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      {current.consecutive_failures > 0 ? <p className="hint">이어서 실패한 자동 결제: {current.consecutive_failures}번</p> : null}
      <Button type="submit" busy={busy}>
        저장
      </Button>
    </form>
  );
}
