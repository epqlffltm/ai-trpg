// web/apps/web/src/pages/trpg/studio/rulebooks/ResourceFields.tsx
// 룰북의 수치(#804) 편집. 마나, 스태미나, 광기 같은 것이다. 줄마다 이름표·이름·최소·최대(기준값 + 능력치, 상한)·시작·
// 쉬기의 변화를 고른다. 더하기·지우기. 검사는 resourcesForm.ts. 템플릿을 고르면 그 템플릿의 예시로 돌아간다.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import type { Ability } from '../../../../api/types';
import {
  newResourceDraft,
  RESOURCES_MAX,
  SHIFT_KINDS,
  SHIFT_LABELS,
  START_LABELS,
  type ResourceDraft,
  type ShiftDraft,
} from './resourcesForm';

type Props = {
  resources: ResourceDraft[];
  /** 최대에 보정을 더할 수 있는 능력치(그 룰북의 규칙의 것) */
  abilities: Ability[];
  hints: Record<string, string>;
  onChange: (resources: ResourceDraft[]) => void;
};

export function ResourceFields({ resources, abilities, hints, onChange }: Props) {
  const replace = (index: number, next: ResourceDraft) => onChange(resources.map((one, at) => (at === index ? next : one)));
  return (
    <fieldset className="scenario-choices">
      <legend>수치</legend>
      <p className="ui-field__hint">
        HP 말고 캐릭터가 가지는 수치입니다(마나, 스태미나 같은 것). 쉬기와 물건의 맞추기가 바꿉니다. {RESOURCES_MAX}개까지 둡니다.
      </p>
      {resources.map((resource, index) => (
        <ResourceRow
          key={index}
          resource={resource}
          abilities={abilities}
          hint={(field) => hints[`resource.${index}.${field}`]}
          onChange={(next) => replace(index, next)}
          onRemove={() => onChange(resources.filter((_, at) => at !== index))}
        />
      ))}
      {hints.resources ? <p className="ui-field__error">{hints.resources}</p> : null}
      <Button variant="quiet" disabled={resources.length >= RESOURCES_MAX} onClick={() => onChange([...resources, newResourceDraft(resources)])}>
        수치 더하기
      </Button>
    </fieldset>
  );
}

type RowProps = {
  resource: ResourceDraft;
  abilities: Ability[];
  hint: (field: string) => string | undefined;
  onChange: (resource: ResourceDraft) => void;
  onRemove: () => void;
};

/** 수치 한 줄 */
function ResourceRow({ resource, abilities, hint, onChange, onRemove }: RowProps) {
  const label = resource.name.trim() || resource.key || '새 수치';
  const set = (changes: Partial<ResourceDraft>) => onChange({ ...resource, ...changes });
  return (
    <fieldset className="scenario-choices" aria-label={`수치 ${label}`}>
      <legend>{label}</legend>
      <TextField label="이름표(영어)" value={resource.key} onChange={(event) => set({ key: event.target.value })} error={hint('key')} />
      <TextField label="이름" value={resource.name} onChange={(event) => set({ name: event.target.value })} error={hint('name')} />
      <TextField label="최소(비우면 0)" inputMode="numeric" value={resource.min} onChange={(event) => set({ min: event.target.value })} error={hint('min')} />
      <TextField label="최대의 기준값" inputMode="numeric" value={resource.base} onChange={(event) => set({ base: event.target.value })} error={hint('base')} />
      <SelectField label="최대에 더할 능력치의 보정" value={resource.ability} onChange={(event) => set({ ability: event.target.value })}>
        <option value="">더하지 않음(고정값)</option>
        {abilities.map((ability) => (
          <option key={ability.key} value={ability.key}>
            {ability.name}
          </option>
        ))}
      </SelectField>
      <TextField label="최대의 상한(선택)" inputMode="numeric" value={resource.cap} onChange={(event) => set({ cap: event.target.value })} error={hint('cap')} />
      <SelectField label="시작" value={resource.start} onChange={(event) => set({ start: event.target.value as ResourceDraft['start'] })}>
        {(Object.keys(START_LABELS) as ResourceDraft['start'][]).map((start) => (
          <option key={start} value={start}>
            {START_LABELS[start]}
          </option>
        ))}
      </SelectField>
      <ShiftField label="짧은 휴식" shift={resource.short} error={hint('short')} onChange={(short) => set({ short })} />
      <ShiftField label="긴 휴식" shift={resource.long} error={hint('long')} onChange={(long) => set({ long })} />
      <Button variant="quiet" onClick={onRemove}>
        {label} 지우기
      </Button>
    </fieldset>
  );
}

type ShiftProps = { label: string; shift: ShiftDraft; error: string | undefined; onChange: (shift: ShiftDraft) => void };

/** 휴식 하나가 수치에 하는 일. 올리기와 내리기에는 양이 있다 */
function ShiftField({ label, shift, error, onChange }: ShiftProps) {
  return (
    <div className="ability-grid">
      <SelectField label={label} value={shift.kind} onChange={(event) => onChange({ ...shift, kind: event.target.value as ShiftDraft['kind'] })}>
        <option value="">{SHIFT_LABELS['']}</option>
        {SHIFT_KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {SHIFT_LABELS[kind]}
          </option>
        ))}
      </SelectField>
      {shift.kind === 'raise' || shift.kind === 'lower' ? (
        <TextField label={`${label}의 양`} inputMode="numeric" value={shift.amount} onChange={(event) => onChange({ ...shift, amount: event.target.value })} error={error} />
      ) : null}
    </div>
  );
}
