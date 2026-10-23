// web/apps/web/src/pages/trpg/room/round/action/TradeFields.tsx
// 돈을 다루는 행동의 칸(#278). 사기(상인, 그 상인이 파는 물건, 개수), 팔기(상인, 값이 있는 내 물건, 개수),
// 돈 건네기(받을 사람, 얼마). 칸 아래에 어림한 값과 가진 돈을 보인다. 값을 정하는 것은 서버다.

import { TextField } from '@ai-trpg/ui';
import type { ActionDraft } from './actionDraft';
import { PAY_MAX_AMOUNT } from './actionDraft';
import { amountLabel, buyingCost, itemPrice, moneyOf, sellingGain } from '../../money';
import {
  heldCount,
  merchants,
  recipients,
  sellableItems,
  stockChoices,
  stockCount,
  stockPrice,
  type ActionContext,
} from './actionOptions';
import { ChoiceSelect } from './ChoiceSelect';
import { CountField } from './ItemActionFields';

type Props = { draft: ActionDraft; ctx: ActionContext; onChange: (changes: Partial<ActionDraft>) => void };

export function BuyFields({ draft, ctx, onChange }: Props) {
  const price = draft.target && draft.item ? stockPrice(ctx, draft.target, draft.item) : null;
  return (
    <div className="ability-grid">
      <ChoiceSelect label="상인" value={draft.target} choices={merchants(ctx)} empty="고르기" onChange={(target) => onChange({ target, item: '' })} />
      {draft.target ? (
        <ChoiceSelect
          label="살 물건"
          value={draft.item}
          choices={stockChoices(ctx, draft.target)}
          empty="고르기"
          onChange={(item) => onChange({ item, count: 1 })}
        />
      ) : null}
      <CountField draft={draft} max={draft.item ? stockCount(ctx, draft.target, draft.item) : 1} onChange={onChange} />
      <MoneyNote ctx={ctx} label="낼 돈" amount={price !== null && Number.isInteger(draft.count) ? buyingCost(price, draft.count) : null} />
    </div>
  );
}

export function SellFields({ draft, ctx, onChange }: Props) {
  const mine = sellableItems(ctx).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
  const price = draft.item ? itemPrice(ctx.table, draft.item) : null;
  const currency = ctx.table.currency;
  return (
    <div className="ability-grid">
      <ChoiceSelect label="상인" value={draft.target} choices={merchants(ctx)} empty="고르기" onChange={(target) => onChange({ target })} />
      <ChoiceSelect label="팔 물건" value={draft.item} choices={mine} empty="고르기" onChange={(item) => onChange({ item, count: 1 })} />
      <CountField draft={draft} max={draft.item ? heldCount(ctx.me, draft.item) : 1} onChange={onChange} />
      <MoneyNote
        ctx={ctx}
        label="받을 돈"
        amount={currency && price !== null && Number.isInteger(draft.count) ? sellingGain(currency, price, draft.count) : null}
      />
    </div>
  );
}

export function PayFields({ draft, ctx, onChange }: Props) {
  return (
    <div className="ability-grid">
      <ChoiceSelect label="받을 사람" value={draft.target} choices={recipients(ctx)} empty="고르기" onChange={(target) => onChange({ target })} />
      <TextField
        label="건넬 돈"
        type="number"
        inputMode="numeric"
        min={1}
        max={Math.min(moneyOf(ctx.me), PAY_MAX_AMOUNT)}
        value={Number.isNaN(draft.amount) ? '' : String(draft.amount)}
        onChange={(event) => onChange({ amount: event.target.value === '' ? Number.NaN : Number(event.target.value) })}
      />
      <MoneyNote ctx={ctx} amount={null} />
    </div>
  );
}

/** "낼 돈 15닢 · 가진 돈 30닢". 값을 아직 모르면 가진 돈만 */
function MoneyNote({ ctx, label = '', amount }: { ctx: ActionContext; label?: string; amount: number | null }) {
  const currency = ctx.table.currency;
  const held = `가진 돈 ${amountLabel(currency, moneyOf(ctx.me))}`;
  return <p className="hint action-note">{amount === null ? held : `${label} ${amountLabel(currency, amount)} · ${held}`}</p>;
}
