// web/apps/web/src/pages/trpg/room/round/action/CheckFields.tsx
// 판정의 칸. 능력과 난이도, 목적(그냥, 타격, 회복), 대상과 크기, 죽이려는가, 노려 치기, 실패의 대가.
// 타격은 장면의 인물이나 내가 선 곳의 몬스터나 해칠 수 있는 동료(#803)에게, 회복은 다른 사람이나 인물에게(비우면 나) 한다.
// 부상을 노리는 것은 인물, 몬스터, 동료에게(동료의 장난이면 짧은 것만). 동료는 죽이려 하지 않는다.
// 타격에는 착용한 무기와 노릴 부위(#276)도 고를 수 있다. 부위와 부상은 함께 노리지 않는다(고르면 다른 쪽을 비운다).

import { Checkbox, Radio } from '@ai-trpg/ui';
import type { ActionDraft, CheckPurpose } from './actionDraft';
import {
  aimableInjuries,
  allyTargets,
  harmTargets,
  healTargets,
  isPrankToward,
  magnitudes,
  myWeapons,
  splitRef,
  strikeSlots,
  type ActionContext,
} from './actionOptions';
import { ChoiceSelect } from './ChoiceSelect';

type Props = { draft: ActionDraft; ctx: ActionContext; onChange: (changes: Partial<ActionDraft>) => void };

const PURPOSES: { value: CheckPurpose; label: string }[] = [
  { value: 'plain', label: '그냥 판정' },
  { value: 'harm', label: '공격' },
  { value: 'recover', label: '회복시키기' },
];

export function CheckFields({ draft, ctx, onChange }: Props) {
  const rules = ctx.table.rules;
  return (
    <>
      <div className="ability-grid">
        <ChoiceSelect
          label="능력"
          value={draft.ability}
          choices={rules.abilities.map((ability) => ({ value: ability.key, label: ability.name }))}
          onChange={(ability) => onChange({ ability })}
        />
        <ChoiceSelect
          label="난이도"
          value={draft.difficulty}
          choices={rules.difficulties.map((entry) => ({ value: entry.key, label: `${entry.name}(${entry.target})` }))}
          onChange={(difficulty) => onChange({ difficulty })}
        />
      </div>
      <fieldset className="choice-list choice-list--inline">
        <legend>무엇을 위한 판정인가</legend>
        {PURPOSES.map((purpose) => (
          <Radio
            key={purpose.value}
            name="check_purpose"
            label={purpose.label}
            checked={draft.purpose === purpose.value}
            onChange={() => onChange({ purpose: purpose.value, target: '' })}
          />
        ))}
      </fieldset>
      {draft.purpose === 'harm' ? <HarmFields draft={draft} ctx={ctx} onChange={onChange} /> : null}
      {draft.purpose === 'recover' ? <RecoverFields draft={draft} ctx={ctx} onChange={onChange} /> : null}
      <ChoiceSelect
        label="실패의 대가(선택)"
        value={draft.risk}
        choices={magnitudes(ctx)}
        empty="없음"
        hint="실패하면 내 캐릭터가 이만큼 다칩니다."
        onChange={(risk) => onChange({ risk })}
      />
    </>
  );
}

function HarmFields({ draft, ctx, onChange }: Props) {
  const targets = [...harmTargets(ctx), ...allyTargets(ctx)];
  const ally = splitRef(draft.target)[0] === 'member';
  const prank = isPrankToward(ctx, draft.target);
  const aims = aimableInjuries(ctx, prank);
  const aimable = (['npc', 'monster'].includes(splitRef(draft.target)[0]) || ally) && aims.length > 0;
  if (targets.length === 0) return <p className="hint">칠 수 있는 대상이 장면에 없습니다.</p>;
  return (
    <>
      <div className="ability-grid">
        <ChoiceSelect label="대상" value={draft.target} choices={targets} empty="고르기" onChange={(target) => onChange({ target })} />
        <ChoiceSelect label="피해" value={draft.magnitude} choices={magnitudes(ctx)} onChange={(magnitude) => onChange({ magnitude })} />
        {aimable ? (
          <ChoiceSelect
            label="노려 치기(선택)"
            value={draft.aim}
            choices={aims}
            empty="노리지 않음"
            onChange={(aim) => onChange({ aim, strike: aim ? '' : draft.strike })}
          />
        ) : null}
        <GearFields draft={draft} ctx={ctx} onChange={onChange} />
      </div>
      {prank ? <p className="hint">장난입니다. HP 1 아래로 내리지 않고 짧은 부상만 입힙니다.</p> : null}
      {ally ? null : (
        <Checkbox
          label="죽이려 한다"
          description="켜지 않으면 HP 가 0 이 될 때 쓰러뜨리기만 합니다."
          checked={draft.lethal}
          onChange={(event) => onChange({ lethal: event.target.checked })}
        />
      )}
    </>
  );
}

/** 무기와 노릴 부위(#276). 고를 것이 없으면 칸을 두지 않는다 */
function GearFields({ draft, ctx, onChange }: Props) {
  const weapons = myWeapons(ctx);
  const slots = strikeSlots(ctx);
  return (
    <>
      {weapons.length > 0 ? (
        <ChoiceSelect label="무기(선택)" value={draft.weapon} choices={weapons} empty="쓰지 않음" onChange={(weapon) => onChange({ weapon })} />
      ) : null}
      {slots.length > 0 ? (
        <ChoiceSelect
          label="노릴 부위(선택)"
          value={draft.strike}
          choices={slots}
          empty="노리지 않음(굴림)"
          hint="노리면 노려 치기의 대가를 치릅니다."
          onChange={(strike) => onChange({ strike, aim: strike ? '' : draft.aim })}
        />
      ) : null}
    </>
  );
}

function RecoverFields({ draft, ctx, onChange }: Props) {
  return (
    <div className="ability-grid">
      <ChoiceSelect
        label="회복받을 쪽"
        value={draft.target}
        choices={healTargets(ctx, true)}
        empty="나"
        onChange={(target) => onChange({ target })}
      />
      <ChoiceSelect label="회복" value={draft.magnitude} choices={magnitudes(ctx)} onChange={(magnitude) => onChange({ magnitude })} />
    </div>
  );
}
