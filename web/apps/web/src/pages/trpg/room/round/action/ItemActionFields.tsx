// web/apps/web/src/pages/trpg/room/round/action/ItemActionFields.tsx
// 물건을 다루는 행동의 칸. 쓰기(소모품, 회복하면 받을 사람), 건네기(받을 사람과 개수), 내려놓기(개수),
// 줍기(내가 선 곳에 놓인 것과 개수), 훔치기와 빼앗기(대상과 그 대상이 지닌 물건).

import { TextField } from '@ai-trpg/ui';
import type { ActionDraft } from './actionDraft';
import { COUNT_MAX } from './actionDraft';
import {
  consumables,
  healTargets,
  heldCount,
  heldItems,
  itemHeals,
  placeItems,
  recipients,
  victimItems,
  victims,
  type ActionContext,
} from './actionOptions';
import { ChoiceSelect } from './ChoiceSelect';

type Props = { draft: ActionDraft; ctx: ActionContext; onChange: (changes: Partial<ActionDraft>) => void };

export function UseFields({ draft, ctx, onChange }: Props) {
  const items = consumables(ctx.me).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
  return (
    <div className="ability-grid">
      <ChoiceSelect label="쓸 물건" value={draft.item} choices={items} empty="고르기" onChange={(item) => onChange({ item })} />
      {draft.item && itemHeals(ctx.table, draft.item) ? (
        <ChoiceSelect label="회복받을 사람" value={draft.target} choices={healTargets(ctx, false)} empty="나" onChange={(target) => onChange({ target })} />
      ) : null}
    </div>
  );
}

export function GiveFields({ draft, ctx, onChange }: Props) {
  return (
    <div className="ability-grid">
      <ChoiceSelect label="건넬 물건" value={draft.item} choices={mine(ctx)} empty="고르기" onChange={(item) => onChange({ item, count: 1 })} />
      <ChoiceSelect label="받을 사람" value={draft.target} choices={recipients(ctx)} empty="고르기" onChange={(target) => onChange({ target })} />
      <CountField draft={draft} max={draft.item ? heldCount(ctx.me, draft.item) : COUNT_MAX} onChange={onChange} />
    </div>
  );
}

export function PutDownFields({ draft, ctx, onChange }: Props) {
  return (
    <div className="ability-grid">
      <ChoiceSelect label="내려놓을 물건" value={draft.item} choices={mine(ctx)} empty="고르기" onChange={(item) => onChange({ item, count: 1 })} />
      <CountField draft={draft} max={draft.item ? heldCount(ctx.me, draft.item) : COUNT_MAX} onChange={onChange} />
    </div>
  );
}

export function TakeFields({ draft, ctx, onChange }: Props) {
  const lying = placeItems(ctx);
  const choices = lying.map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
  const max = lying.find((item) => item.entry_id === draft.item)?.count ?? COUNT_MAX;
  return (
    <div className="ability-grid">
      <ChoiceSelect label="주울 물건" value={draft.item} choices={choices} empty="고르기" onChange={(item) => onChange({ item, count: 1 })} />
      <CountField draft={draft} max={max} onChange={onChange} />
    </div>
  );
}

export function VictimFields({ draft, ctx, onChange, kind }: Props & { kind: 'steal' | 'loot' }) {
  const targets = victims(ctx, kind);
  return (
    <div className="ability-grid">
      <ChoiceSelect
        label={kind === 'steal' ? '훔칠 대상' : '가져올 대상'}
        value={draft.target}
        choices={targets}
        empty="고르기"
        onChange={(target) => onChange({ target, item: '' })}
      />
      {draft.target ? (
        <ChoiceSelect label="물건" value={draft.item} choices={victimItems(ctx, draft.target)} empty="고르기" onChange={(item) => onChange({ item })} />
      ) : null}
    </div>
  );
}

function mine(ctx: ActionContext) {
  return heldItems(ctx.me).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
}

export function CountField({ draft, max, onChange }: { draft: ActionDraft; max: number; onChange: Props['onChange'] }) {
  return (
    <TextField
      label="개수"
      type="number"
      inputMode="numeric"
      min={1}
      max={Math.min(max, COUNT_MAX)}
      value={Number.isNaN(draft.count) ? '' : String(draft.count)}
      onChange={(event) => onChange({ count: event.target.value === '' ? Number.NaN : Number(event.target.value) })}
    />
  );
}
