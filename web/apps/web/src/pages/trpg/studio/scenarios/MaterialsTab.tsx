// web/apps/web/src/pages/trpg/studio/scenarios/MaterialsTab.tsx
// 시나리오의 재료 탭(B9): 내 룰북, 세계관, 로어북, 몬스터 모음 가운데서 고른다. 남의 재료는 고를 거리에 없다.
// 룰북은 게시할 때 꼭 있어야 한다. 로어북이나 몬스터 모음을 떼면 그것을 가리키던 규칙이 게시 점검에 문제로 나온다.

import { Checkbox, SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { StudioKind } from '../../../../api/studio';
import type { ScenarioDetail } from '../../../../api/types';
import { kindText, studioNewPath } from '../studioKinds';
import { MAX_BESTIARIES, MAX_LOREBOOKS, materialsDraft, toggleId, toMaterialsBody, withChosen, type MaterialsDraft } from './materialsForm';
import { ScenarioForm } from './ScenarioForm';
import { choicesQuery } from './scenarioQueries';
import { useScenarioSave } from './useScenarioSave';

export function MaterialsTab({ scenario }: { scenario: ScenarioDetail }) {
  const [draft, setDraft] = useState<MaterialsDraft>(() => materialsDraft(scenario));
  const saving = useScenarioSave(scenario.id);

  async function submit() {
    const saved = await saving.save(toMaterialsBody(draft));
    if (saved) setDraft(materialsDraft(saved));
  }

  return (
    <ScenarioForm label="재료" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={false} onSubmit={() => void submit()}>
      <p className="hint">내가 만든 재료에서 고릅니다. 로어북이나 몬스터 모음을 떼면 그 안의 것을 가리키던 규칙이 게시 점검에 문제로 나옵니다.</p>
      <OneChoice
        kind="rulebooks"
        value={draft.rulebookId}
        onChange={(rulebookId) => setDraft((current) => ({ ...current, rulebookId }))}
        hint="게시하려면 꼭 있어야 합니다. 능력치, 판정, 방어 같은 규칙이 여기서 옵니다."
      />
      <OneChoice
        kind="worlds"
        value={draft.worldId}
        onChange={(worldId) => setDraft((current) => ({ ...current, worldId }))}
        hint="고르지 않아도 됩니다. 서술하는 AI 가 배경으로 읽습니다."
      />
      <ManyChoices
        kind="lorebooks"
        chosen={draft.lorebookIds}
        max={MAX_LOREBOOKS}
        onToggle={(id) => setDraft((current) => ({ ...current, lorebookIds: toggleId(current.lorebookIds, id, MAX_LOREBOOKS) }))}
      />
      <ManyChoices
        kind="bestiaries"
        chosen={draft.bestiaryIds}
        max={MAX_BESTIARIES}
        onToggle={(id) => setDraft((current) => ({ ...current, bestiaryIds: toggleId(current.bestiaryIds, id, MAX_BESTIARIES) }))}
      />
    </ScenarioForm>
  );
}

type OneProps = { kind: StudioKind; value: string; onChange: (id: string) => void; hint: string };

/** 하나만 고르는 재료(룰북, 세계관). 비우면 뗀다 */
function OneChoice({ kind, value, onChange, hint }: OneProps) {
  const choices = useQuery(choicesQuery(kind));
  const text = kindText(kind);
  const options = withChosen(choices.data?.items ?? [], value ? [value] : []);
  return (
    <>
      <SelectField
        label={text.label}
        name={kind}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        hint={choices.isError ? '목록을 불러오지 못했습니다.' : hint}
      >
        <option value="">고르지 않음</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.title ?? '목록에 없는 재료'}
          </option>
        ))}
      </SelectField>
      {choices.isSuccess && choices.data.total === 0 ? <EmptyChoices kind={kind} /> : null}
    </>
  );
}

type ManyProps = { kind: StudioKind; chosen: string[]; max: number; onToggle: (id: string) => void };

/** 여럿을 고르는 재료(로어북, 몬스터 모음). 가득 차면 고르지 않은 것을 끈다 */
function ManyChoices({ kind, chosen, max, onToggle }: ManyProps) {
  const choices = useQuery(choicesQuery(kind));
  const text = kindText(kind);
  const options = withChosen(choices.data?.items ?? [], chosen);
  const full = chosen.length >= max;
  return (
    <fieldset className="scenario-choices">
      <legend>
        {text.label} <span className="hint">({chosen.length} / {max})</span>
      </legend>
      {choices.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {choices.isError ? <p className="ui-field__error">목록을 불러오지 못했습니다.</p> : null}
      {choices.isSuccess && choices.data.total === 0 ? <EmptyChoices kind={kind} /> : null}
      {options.map((option) => (
        <Checkbox
          key={option.id}
          label={option.title ?? '목록에 없는 재료'}
          checked={chosen.includes(option.id)}
          disabled={full && !chosen.includes(option.id)}
          onChange={() => onToggle(option.id)}
        />
      ))}
    </fieldset>
  );
}

function EmptyChoices({ kind }: { kind: StudioKind }) {
  const text = kindText(kind);
  return (
    <p className="hint">
      {text.empty} <Link to={studioNewPath(kind)}>{text.first}</Link>
    </p>
  );
}
