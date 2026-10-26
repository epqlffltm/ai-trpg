// web/apps/web/src/pages/trpg/room/round/action/ActionFields.tsx
// 선언에 붙일 행동. 종류를 고르면 그 종류의 칸이 열린다. 고를 수 있는 종류는 actionOptions.ts 의 availableKinds 다.
// 쓰러졌거나 죽었으면 행동을 붙이지 못한다고 알린다(글만 낸다).

import { Radio, TextField } from '@ai-trpg/ui';
import type { ActionDraft } from './actionDraft';
import { NAME_GUESS_MAX, WAIT_MAX_MINUTES } from './actionDraft';
import {
  availableKinds,
  climbs,
  canAttachAction,
  coverHere,
  carriable,
  hereId,
  nameablePeople,
  patients,
  treatableInjuries,
  ways,
  type ActionContext,
  type ActionKind,
} from './actionOptions';
import { ACTION_LABELS } from './actionLabels';
import { AidSelect } from './AidSelect';
import { CheckFields } from './CheckFields';
import { DoorActionFields } from './DoorActionFields';
import { ChoiceSelect } from './ChoiceSelect';
import { GiveFields, PutDownFields, TakeFields, ThrowFields, UseFields, VictimFields } from './ItemActionFields';
import { BuyFields, PayFields, SellFields } from './TradeFields';
import { minutesLabel, wayNotes } from '../../status/statusView';

type Props = {
  draft: ActionDraft;
  ctx: ActionContext;
  onChange: (changes: Partial<ActionDraft>) => void;
  error?: string | null;
};

export function ActionFields({ draft, ctx, onChange, error }: Props) {
  if (!canAttachAction(ctx.me)) return <p className="hint">캐릭터가 쓰러졌거나 죽어 행동을 붙일 수 없습니다. 글만 낼 수 있습니다.</p>;
  const kinds = availableKinds(ctx);
  return (
    <div className="action-fields">
      <ChoiceSelect
        label="행동"
        value={draft.kind === 'none' ? '' : draft.kind}
        choices={kinds.map((kind) => ({ value: kind, label: ACTION_LABELS[kind] }))}
        empty="행동 없이(글만)"
        hint="한 라운드에 행동은 하나입니다. 결과는 라운드를 마감할 때 서버가 정합니다."
        onChange={(kind) => onChange({ kind: (kind || 'none') as ActionKind | 'none' })}
      />
      <KindFields draft={draft} ctx={ctx} onChange={onChange} />
      {error ? <p className="ui-field__error">{error}</p> : null}
    </div>
  );
}

function KindFields({ draft, ctx, onChange }: Omit<Props, 'error'>) {
  switch (draft.kind) {
    case 'check':
      return <CheckFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'treat':
      return <TreatFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'name':
      return <NameFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'use':
      return <UseFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'give':
      return <GiveFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'throw':
      return <ThrowFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'put_down':
      return <PutDownFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'take':
      return <TakeFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'steal':
    case 'loot':
      return <VictimFields draft={draft} ctx={ctx} onChange={onChange} kind={draft.kind} />;
    case 'move':
      return <MoveFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'search':
      return <p className="hint">지금 있는 곳에서 숨긴 길과 물건을 찾습니다. 무엇으로 굴리는지는 판이 정합니다.</p>;
    case 'cover':
      return <CoverHint ctx={ctx} />;
    case 'rest':
      return <RestFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'wait':
      return <WaitFields draft={draft} onChange={onChange} />;
    case 'buy':
      return <BuyFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'sell':
      return <SellFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'pay':
      return <PayFields draft={draft} ctx={ctx} onChange={onChange} />;
    case 'lock':
    case 'unlock':
    case 'pick':
    case 'force':
    case 'repair':
    case 'replace':
      return <DoorActionFields kind={draft.kind} draft={draft} ctx={ctx} onChange={onChange} />;
    default:
      return null;
  }
}

type FieldProps = Omit<Props, 'error'>;

/** 엄폐하기(#276). 고를 것이 없다. 이 라운드 동안 그 장소의 커버로 세이브를 받고, 공격하지 못한다 */
function CoverHint({ ctx }: { ctx: ActionContext }) {
  return (
    <p className="hint">
      이 라운드 동안 지금 있는 곳의 커버({coverHere(ctx)})로 커버 세이브를 받습니다. 몬스터가 먼저 쳐도 듭니다. 이 라운드에는 공격하지
      못합니다.
    </p>
  );
}

function TreatFields({ draft, ctx, onChange }: FieldProps) {
  const injuries = treatableInjuries(ctx, draft.target);
  return (
    <div className="ability-grid">
      <ChoiceSelect label="치료받을 쪽" value={draft.target} choices={patients(ctx)} onChange={(target) => onChange({ target, injury: '' })} />
      {injuries.length > 0 ? (
        <ChoiceSelect label="부상" value={draft.injury} choices={injuries} empty="고르기" onChange={(injury) => onChange({ injury })} />
      ) : (
        <p className="hint">치료할 수 있는(오래 가는) 부상이 없습니다.</p>
      )}
      <AidSelect act="treat" value={draft.item} ctx={ctx} onChange={(item) => onChange({ item })} />
    </div>
  );
}

function NameFields({ draft, ctx, onChange }: FieldProps) {
  return (
    <div className="ability-grid">
      <TextField label="짚을 이름" maxLength={NAME_GUESS_MAX} value={draft.guess} onChange={(event) => onChange({ guess: event.target.value })} />
      <ChoiceSelect label="누구의 이름인가" value={draft.npc} choices={nameablePeople(ctx)} empty="이런 이름의 인물이 있다" onChange={(npc) => onChange({ npc })} />
    </div>
  );
}

function MoveFields({ draft, ctx, onChange }: FieldProps) {
  const here = hereId(ctx) ?? '';
  const choices = ways(ctx).map((way) => {
    const notes = [...(way.minutes === null ? [] : [minutesLabel(way.minutes)]), ...wayNotes(way, here, ctx.table.rules)];
    return { value: way.placeId, label: notes.length > 0 ? `${way.name}(${notes.join(' · ')})` : way.name };
  });
  const downed = carriable(ctx);
  return (
    <div className="ability-grid">
      <ChoiceSelect label="갈 곳" value={draft.place} choices={choices} empty="고르기" onChange={(place) => onChange({ place })} />
      {downed.length > 0 ? (
        <ChoiceSelect label="업고 갈 동료(선택)" value={draft.carry} choices={downed} empty="혼자 간다" onChange={(carry) => onChange({ carry })} />
      ) : null}
      {draft.place && climbs(ctx, draft.place) ? <AidSelect act="cross" value={draft.item} ctx={ctx} onChange={(item) => onChange({ item })} /> : null}
    </div>
  );
}

function RestFields({ draft, ctx, onChange }: FieldProps) {
  const rest = ctx.table.rules.rest;
  if (!rest) return null;
  return (
    <fieldset className="choice-list choice-list--inline">
      <legend>얼마나 쉬나</legend>
      <Radio name="rest_length" label={`짧게(${minutesLabel(rest.short.minutes)})`} checked={draft.length === 'short'} onChange={() => onChange({ length: 'short' })} />
      <Radio name="rest_length" label={`길게(${minutesLabel(rest.long.minutes)})`} checked={draft.length === 'long'} onChange={() => onChange({ length: 'long' })} />
    </fieldset>
  );
}

function WaitFields({ draft, onChange }: Pick<FieldProps, 'draft' | 'onChange'>) {
  return (
    <TextField
      label="기다릴 시간(분)"
      type="number"
      inputMode="numeric"
      min={1}
      max={WAIT_MAX_MINUTES}
      value={Number.isNaN(draft.minutes) ? '' : String(draft.minutes)}
      onChange={(event) => onChange({ minutes: event.target.value === '' ? Number.NaN : Number(event.target.value) })}
    />
  );
}
