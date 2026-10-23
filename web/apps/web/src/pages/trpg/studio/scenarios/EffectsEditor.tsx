// web/apps/web/src/pages/trpg/studio/scenarios/EffectsEditor.tsx
// 사건의 효과들을 고치는 칸(B9 퀘스트·사건 탭). 효과마다 종류를 고르면 그 종류의 칸이 나온다.
// 캐릭터 옮기기(옮겨 갈 장소, 그 장소에 선 사람만이면 그 장소), 인물 옮기기(인물, 장소), 길의 문(판의 길, 장치). 검사는 happeningForm.ts.

import { Button, SelectField } from '@ai-trpg/ui';
import type { DoorDevice, RouteRule } from '../../../../api/types';
import type { Targets } from './conditionsForm';
import { EFFECT_KINDS, effectKindLabel, MAX_EFFECTS, newEffect, routeKey, type EffectDraft, type EffectKind } from './happeningForm';
import type { EntryChoice } from './useLoreEntries';

type Props = {
  drafts: EffectDraft[];
  onChange: (drafts: EffectDraft[]) => void;
  targets: Targets;
  routes: RouteRule[];
  hints: Record<number, string>;
};

export function EffectsEditor({ drafts, onChange, targets, routes, hints }: Props) {
  const change = (index: number, changes: Partial<EffectDraft>) => onChange(drafts.map((one, at) => (at === index ? { ...one, ...changes } : one)));
  const place = (id: string) => targets.places.find((one) => one.id === id)?.name ?? '(찾을 수 없음)';
  return (
    <div className="scenario-stacks">
      {drafts.map((draft, index) => (
        <fieldset key={index} className="scenario-stack">
          <legend>효과 {index + 1}</legend>
          <SelectField label="종류" value={draft.kind} onChange={(event) => change(index, { ...newEffect(), kind: event.target.value as EffectKind })}>
            {EFFECT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {effectKindLabel(kind)}
              </option>
            ))}
          </SelectField>
          <div className="scenario-players__row">
            {draft.kind === 'move' ? (
              <>
                <ChoiceSelect label="옮겨 갈 장소" value={draft.toPlace} choices={targets.places} onChange={(toPlace) => change(index, { toPlace })} />
                <ChoiceSelect label="누구를" value={draft.fromPlace} choices={targets.places} empty="모든 캐릭터" prefix="그 장소에 선 사람: " onChange={(fromPlace) => change(index, { fromPlace })} />
              </>
            ) : null}
            {draft.kind === 'move_npc' ? (
              <>
                <ChoiceSelect label="인물" value={draft.npc} choices={targets.npcs} onChange={(npc) => change(index, { npc })} />
                <ChoiceSelect label="옮겨 갈 장소" value={draft.toPlace} choices={targets.places} onChange={(toPlace) => change(index, { toPlace })} />
              </>
            ) : null}
            {draft.kind === 'lock_route' || draft.kind === 'unlock_route' || draft.kind === 'repair_route' ? (
              <SelectField label="길" value={draft.route} onChange={(event) => change(index, { route: event.target.value })}>
                <option value="">고르기</option>
                {routes.map((route) => (
                  <option key={routeKey(route.from_place, route.to_place)} value={routeKey(route.from_place, route.to_place)}>
                    {place(route.from_place)}–{place(route.to_place)}
                    {route.lock || route.bar ? '' : '(문 없음)'}
                  </option>
                ))}
              </SelectField>
            ) : null}
            {draft.kind === 'lock_route' || draft.kind === 'unlock_route' ? (
              <SelectField label="장치" value={draft.device} onChange={(event) => change(index, { device: event.target.value as '' | DoorDevice })}>
                <option value="">그 문의 장치 모두</option>
                <option value="lock">자물쇠</option>
                <option value="bar">빗장</option>
              </SelectField>
            ) : null}
          </div>
          {hints[index] ? <p className="ui-field__error">{hints[index]}</p> : null}
          <Button variant="quiet" aria-label={`효과 ${index + 1} 지우기`} onClick={() => onChange(drafts.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      <p>
        <Button variant="secondary" disabled={drafts.length >= MAX_EFFECTS} onClick={() => onChange([...drafts, newEffect()])}>
          효과 더하기
        </Button>{' '}
        <span className="hint">
          {drafts.length} / {MAX_EFFECTS}
        </span>
      </p>
    </div>
  );
}

type ChoiceProps = { label: string; value: string; choices: EntryChoice[]; onChange: (id: string) => void; empty?: string; prefix?: string };

function ChoiceSelect({ label, value, choices, onChange, empty = '고르기', prefix = '' }: ChoiceProps) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{empty}</option>
      {value !== '' && !choices.some((one) => one.id === value) ? <option value={value}>(찾을 수 없음)</option> : null}
      {choices.map((one) => (
        <option key={one.id} value={one.id}>
          {prefix}
          {one.name}
        </option>
      ))}
    </SelectField>
  );
}
