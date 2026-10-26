// web/apps/web/src/pages/trpg/room/round/action/ItemActionFields.tsx
// 물건을 다루는 행동의 칸. 쓰기(소모품, 효과가 있으면 받을 쪽: 나, 동료, 인물, 몬스터. #800), 건네기(받을 사람과 개수), 내려놓기(개수),
// 줍기(내가 선 곳에 놓인 것과 개수), 훔치기와 빼앗기(대상과 그 대상이 지닌 물건),
// 던지기(#277, #801. 지닌 물건 아무것이나와 맞힐 대상. 판정은 물건이나 룰북에 적혀 있어 보이기만 한다).
// 해로운 물건을 동료에게 쓰고 던지는 것(#803)은 해칠 수 있는 동료만 고르고, 장난이면 그렇게 알린다.

import { Checkbox, TextField } from '@ai-trpg/ui';
import type { TableDetail } from '../../../../../api/types';
import type { ActionDraft } from './actionDraft';
import { COUNT_MAX } from './actionDraft';
import {
  consumables,
  heldCount,
  heldItems,
  isPrankToward,
  itemDamages,
  itemHarms,
  itemTakesTarget,
  splitRef,
  useTargets,
  placeItems,
  recipients,
  throwables,
  throwTargets,
  victimItems,
  victims,
  type ActionContext,
} from './actionOptions';
import { effectsLabel } from '../../status/statusView';
import { ChoiceSelect } from './ChoiceSelect';

type Props = { draft: ActionDraft; ctx: ActionContext; onChange: (changes: Partial<ActionDraft>) => void };

export function UseFields({ draft, ctx, onChange }: Props) {
  const items = consumables(ctx.me).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
  return (
    <div className="ability-grid">
      <ChoiceSelect label="쓸 물건" value={draft.item} choices={items} empty="고르기" onChange={(item) => onChange({ item, target: '' })} />
      {draft.item && itemTakesTarget(ctx.table, draft.item) ? <UseTargetFields draft={draft} ctx={ctx} onChange={onChange} /> : null}
    </div>
  );
}

/** 물건을 쓸 쪽과, 인물이나 몬스터면 맞히는 판정의 말과 죽이려 한다(피해가 있는 물건) */
function UseTargetFields({ draft, ctx, onChange }: Props) {
  const aimed = ['npc', 'monster'].includes(splitRef(draft.target)[0]);
  return (
    <>
      <ChoiceSelect label="쓸 쪽" value={draft.target} choices={useTargets(ctx, draft.item)} empty="나" onChange={(target) => onChange({ target })} />
      {aimed ? <p className="hint">인물과 몬스터에게는 맞히는 판정을 굴립니다. 빗나가도 물건은 하나 없어집니다.</p> : null}
      {isPrankToward(ctx, draft.target) && itemHarms(ctx.table, draft.item) ? (
        <p className="hint">장난입니다. HP 1 아래로 내리지 않고 짧은 부상만 입힙니다.</p>
      ) : null}
      {aimed && itemDamages(ctx.table, draft.item) ? (
        <Checkbox
          label="죽이려 한다"
          description="켜지 않으면 HP 가 0 이 될 때 쓰러뜨리기만 합니다."
          checked={draft.lethal}
          onChange={(event) => onChange({ lethal: event.target.checked })}
        />
      ) : null}
    </>
  );
}

export function ThrowFields({ draft, ctx, onChange }: Props) {
  const items = throwables(ctx).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }));
  const terms = draft.item ? throwTerms(ctx.table, draft.item) : null;
  return (
    <>
      <div className="ability-grid">
        <ChoiceSelect label="던질 물건" value={draft.item} choices={items} empty="고르기" onChange={(item) => onChange({ item })} />
        <ChoiceSelect
          label="맞힐 대상"
          value={draft.target}
          choices={throwTargets(ctx, draft.item)}
          empty="고르기"
          onChange={(target) => onChange({ target })}
        />
      </div>
      {terms ? <p className="hint">{terms}</p> : null}
      {isPrankToward(ctx, draft.target) && itemHarms(ctx.table, draft.item) ? (
        <p className="hint">장난입니다. HP 1 아래로 내리지 않고 짧은 부상만 입힙니다.</p>
      ) : null}
      {draft.item && itemDamages(ctx.table, draft.item) && splitRef(draft.target)[0] !== 'member' ? (
        <Checkbox
          label="죽이려 한다"
          description="켜지 않으면 HP 가 0 이 될 때 쓰러뜨리기만 합니다."
          checked={draft.lethal}
          onChange={(event) => onChange({ lethal: event.target.checked })}
        />
      ) : null}
    </>
  );
}

/**
 * 던지는 판정의 글(#801). 물건에 적힌 것이나 룰북의 맞히는 판정이다. 맞으면 그 물건의 효과가 든다.
 * "민첩 · 보통으로 던집니다. 맞으면 피해 보통(1d8). 맞든 빗나가든 하나 없어집니다."
 */
export function throwTerms(table: TableDetail, entryId: string): string | null {
  const thrown = table.items.find((item) => item.entry_id === entryId)?.throw ?? table.rules.item_check;
  if (!thrown) return null;
  const rules = table.rules;
  const ability = rules.abilities.find((entry) => entry.key === thrown.ability)?.name ?? thrown.ability;
  const key = thrown.difficulty ?? rules.default_difficulty;
  const difficulty = rules.difficulties.find((entry) => entry.key === key)?.name ?? key;
  const effects = effectsLabel(table, entryId);
  const hit = effects ? `맞으면 ${effects}.` : '맞아도 아무 효과가 없습니다.';
  return `${ability} · ${difficulty}으로 던집니다. ${hit} 맞든 빗나가든 하나 없어집니다.`;
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
