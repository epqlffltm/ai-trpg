// web/apps/web/src/pages/wallet/CardPanel.tsx
// 자동 충전(#980)에 쓸 카드. 등록한 카드(카드사 코드, 가린 번호)를 보이고, 등록하거나 바꾸거나 지운다.
// 등록 창은 결제 대행사의 것이다. 지금은 시험용(VITE_PAYMENT_GATEWAY=fake)만 있다. 결과를 고르면 그 앞머리로 인증 키를 지어 보낸다.
// 실제 등록 창(토스페이먼츠)도 마지막에 인증 키 하나를 넘긴다. 받는 쪽(onRegister)은 같다.
// 지우면 자동 충전도 꺼진다(서버가 함께 끈다).

import { Button, SelectField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { PaymentCard } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import type { GatewayKind } from '../charge/paymentGateway';
import { FAKE_CARD_OUTCOMES, FAKE_CHARGE_MARKS, fakeAuthKey } from './autoChargeView';

type Props = {
  card: PaymentCard | null;
  gateway: GatewayKind;
  busy: boolean;
  onRegister: (authKey: string) => void;
  onRemove: () => void;
};

export function CardPanel({ card, gateway, busy, onRegister, onRemove }: Props) {
  const [opened, setOpened] = useState(false);
  const [mark, setMark] = useState<string>('');
  const [confirming, setConfirming] = useState(false);

  function register(prefix: string) {
    setOpened(false);
    onRegister(fakeAuthKey(prefix, mark, crypto.randomUUID()));
  }

  return (
    <div className="auto-charge__card">
      <h3>카드</h3>
      {card ? (
        <p>
          {card.number} · 카드사 {card.issuer_code} · {formatDateTime(card.registered_at)}에 등록
        </p>
      ) : (
        <p>등록한 카드가 없습니다.</p>
      )}
      {gateway !== 'fake' ? <p className="hint">카드 등록은 준비 중입니다.</p> : null}
      {gateway === 'fake' && !opened ? (
        <Button variant="secondary" disabled={busy} onClick={() => setOpened(true)}>
          {card ? '카드 바꾸기' : '카드 등록'}
        </Button>
      ) : null}
      {opened ? (
        <section className="checkout" aria-labelledby="card-checkout-heading">
          <h4 id="card-checkout-heading">시험용 카드 등록 창</h4>
          <p className="hint">실제 카드가 아닙니다. 등록의 결과를 골라 흐름을 봅니다.</p>
          <SelectField label="이 카드로 자동 결제할 때" value={mark} onChange={(event) => setMark(event.target.value)}>
            {FAKE_CHARGE_MARKS.map((one) => (
              <option key={one.mark} value={one.mark}>
                {one.label}
              </option>
            ))}
          </SelectField>
          <div className="checkout__outcomes">
            {FAKE_CARD_OUTCOMES.map((outcome) => (
              <Button
                key={outcome.prefix}
                variant={outcome.prefix === 'fake_card_ok_' ? 'primary' : 'secondary'}
                disabled={busy}
                onClick={() => register(outcome.prefix)}
              >
                {outcome.label}
              </Button>
            ))}
          </div>
          <Button variant="quiet" onClick={() => setOpened(false)}>
            그만두기
          </Button>
        </section>
      ) : null}
      {card && !confirming ? (
        <Button variant="quiet" disabled={busy} onClick={() => setConfirming(true)}>
          카드 지우기
        </Button>
      ) : null}
      {card && confirming ? (
        <p>
          카드를 지우면 자동 충전도 꺼집니다.{' '}
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => {
              setConfirming(false);
              onRemove();
            }}
          >
            지우기
          </Button>{' '}
          <Button variant="quiet" onClick={() => setConfirming(false)}>
            그만두기
          </Button>
        </p>
      ) : null}
    </div>
  );
}
