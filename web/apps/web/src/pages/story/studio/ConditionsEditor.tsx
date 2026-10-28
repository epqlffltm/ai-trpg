// web/apps/web/src/pages/story/studio/ConditionsEditor.tsx
// 조건 목록의 칸(D7). 맞추는 법(모두, 하나라도)과 조건마다 종류·대상·값·수를 표처럼 고른다. 글로 식을 적지 않는다.
// 일정의 줄, 고백, 이벤트, 엔딩이 함께 쓴다. 이름표 앞에 쓰는 쪽의 이름(prefix)을 붙여 같은 화면의 여러 목록을 가른다.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import {
  addCondition,
  changeCondition,
  CONDITION_KIND_ORDER,
  CONDITION_KINDS,
  CONDITIONS_MAX,
  removeCondition,
  targetChoices,
  valueChoices,
  type ConditionChoices,
  type ConditionsDraft,
} from './conditionsForm';
import { labelOr } from './worldLabels';

type Props = {
  /** 이름표 앞에 붙는 말("미나의 일정 1") */
  prefix: string;
  draft: ConditionsDraft;
  choices: ConditionChoices;
  hints: Record<number, string>;
  onChange: (draft: ConditionsDraft) => void;
  /** 비었을 때의 뜻("늘 맞는다" 같은 것) */
  emptyText: string;
};

export function ConditionsEditor({ prefix, draft, choices, hints, onChange, emptyText }: Props) {
  return (
    <fieldset className="scenario-choices">
      <legend>{prefix}의 조건</legend>
      {draft.items.length === 0 ? <p className="hint">{emptyText}</p> : null}
      {draft.items.length > 1 ? (
        <SelectField label={`${prefix}의 조건을 맞추는 법`} value={draft.match} onChange={(event) => onChange({ ...draft, match: event.target.value as ConditionsDraft['match'] })}>
          <option value="all">모두 맞아야 한다</option>
          <option value="any">하나라도 맞으면 된다</option>
        </SelectField>
      ) : null}
      <ol className="plain-list" aria-label={`${prefix}의 조건`}>
        {draft.items.map((item, index) => {
          const spec = CONDITION_KINDS[item.kind];
          const label = `${prefix}의 조건 ${index + 1}`;
          return (
            <li key={index} className="scenario-opening">
              <SelectField label={`${label}의 종류`} value={item.kind} onChange={(event) => onChange(changeCondition(draft, index, { kind: event.target.value as typeof item.kind }))}>
                {CONDITION_KIND_ORDER.map((kind) => (
                  <option key={kind} value={kind}>
                    {CONDITION_KINDS[kind].label}
                  </option>
                ))}
              </SelectField>
              {spec.target ? (
                <SelectField label={`${label}의 대상`} value={item.target} onChange={(event) => onChange(changeCondition(draft, index, { target: event.target.value }))}>
                  <option value="">고르지 않음</option>
                  {targetChoices(item.kind, choices).map((choice, at) => (
                    <option key={choice.id} value={choice.id}>
                      {labelOr(choice.name, `${at + 1}번째`)}
                    </option>
                  ))}
                </SelectField>
              ) : null}
              {spec.value ? (
                <SelectField label={`${label}의 ${spec.value === 'stage' ? '단계' : '물건'}`} value={item.value} onChange={(event) => onChange(changeCondition(draft, index, { value: event.target.value }))}>
                  <option value="">고르지 않음</option>
                  {valueChoices(item, choices).map((choice, at) => (
                    <option key={choice.id} value={choice.id}>
                      {labelOr(choice.name, `${at + 1}번째`)}
                    </option>
                  ))}
                </SelectField>
              ) : null}
              {spec.count ? (
                <TextField label={`${label}의 수(${spec.count})`} inputMode="numeric" value={item.count} onChange={(event) => onChange(changeCondition(draft, index, { count: event.target.value }))} />
              ) : null}
              {hints[index] ? <p className="ui-field__error">{hints[index]}</p> : null}
              <div className="form-actions">
                <Button variant="quiet" aria-label={`${label} 지우기`} onClick={() => onChange(removeCondition(draft, index))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.items.length >= CONDITIONS_MAX} onClick={() => onChange(addCondition(draft))}>
          {prefix}의 조건 더하기
        </Button>
      </p>
    </fieldset>
  );
}
