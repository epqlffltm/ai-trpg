// web/apps/web/src/pages/trpg/studio/scenarios/CharactersTab.tsx
// 시나리오의 캐릭터 탭(B9): 추천 인원, 캐릭터 방식, 다시 굴리기, 기본 시트, 능력치를 정하는 방식의 최대 HP(탭의 저장),
// 그리고 프리젠(창에서 따로 저장, PregensSection). 시트의 칸은 저장된 룰북의 능력치에서 만든다.
// 룰북이 없으면 시트를 적을 수 없다고 알리고 재료 탭으로 가는 길을 둔다.

import { Button, Checkbox, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { CharacterMode, Ruleset, ScenarioDetail } from '../../../../api/types';
import { characterModeLabel } from '../../labels';
import { rulebookQuery } from '../rulebooks/rulebookQueries';
import {
  CHARACTER_MODES,
  charactersDraft,
  charactersHints,
  hpFormulaText,
  MAX_PLAYERS,
  modeWarnings,
  toCharactersBody,
  toggleMode,
  usesDefaultSheet,
  usesPlayerMadeHp,
  type CharactersDraft,
} from './charactersForm';
import { PregensSection } from './PregensSection';
import { ScenarioForm } from './ScenarioForm';
import type { ScenarioTab } from './scenarioTabs';
import { sheetFieldHints } from './sheetForm';
import { SheetFields } from './SheetFields';
import { useScenarioSave } from './useScenarioSave';

const MODE_HINTS: Record<CharacterMode, string> = {
  pregen: '아래의 프리젠 가운데 고릅니다.',
  custom: '이름과 설명만 쓰고, 숫자는 기본 시트를 받습니다.',
  manual: '능력치를 룰북의 범위 안에서 직접 적습니다.',
  point_buy: '룰북의 총점 안에서 능력치를 삽니다.',
  rolled: '서버가 주사위로 점수를 굴리고, 플레이어가 능력치에 놓습니다.',
};

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function CharactersTab({ scenario, goTo }: Props) {
  const rulebook = useQuery({ ...rulebookQuery(scenario.rulebook_id ?? ''), enabled: scenario.rulebook_id !== null });
  if (scenario.rulebook_id !== null && rulebook.isPending) return <p aria-busy="true">룰북을 불러오는 중</p>;
  const rules = rulebook.data?.rules ?? null;
  return (
    <>
      {scenario.rulebook_id === null ? (
        <Notice>
          능력치는 룰북이 정해서, 룰북을 고르기 전에는 시트를 적을 수 없습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {rulebook.isError ? <Notice tone="error">룰북을 불러오지 못해 시트를 적을 수 없습니다.</Notice> : null}
      {/* 룰북이 바뀌면 시트의 칸이 바뀌므로 폼을 새로 만든다 */}
      <CharactersForm key={scenario.rulebook_id ?? 'none'} scenario={scenario} rules={rules} />
      <PregensSection scenario={scenario} rules={rules} />
    </>
  );
}

function CharactersForm({ scenario, rules }: { scenario: ScenarioDetail; rules: Ruleset | null }) {
  const [draft, setDraft] = useState<CharactersDraft>(() => charactersDraft(scenario, rules));
  const saving = useScenarioSave(scenario.id);
  const hints = charactersHints(draft, rules);

  function update(changes: Partial<CharactersDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit() {
    const saved = await saving.save(toCharactersBody(draft, rules));
    if (saved) setDraft(charactersDraft(saved, rules));
  }

  return (
    <ScenarioForm
      label="캐릭터"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <PlayersFields draft={draft} hint={hints.recommended_players} update={update} />
      <ModesFields draft={draft} rules={rules} hint={hints.character_modes} update={update} />
      {rules && draft.defaultSheet && usesDefaultSheet(draft.modes) ? (
        <SheetFields
          legend="기본 시트(이름과 설명만 쓰는 캐릭터가 받는 숫자)"
          rules={rules}
          draft={draft.defaultSheet}
          hints={sheetFieldHints(hints)}
          onChange={(defaultSheet) => update({ defaultSheet })}
        />
      ) : null}
      {usesPlayerMadeHp(draft.modes) ? <HpFields draft={draft} rules={rules} hints={hints} update={update} /> : null}
    </ScenarioForm>
  );
}

type FieldsProps = { draft: CharactersDraft; update: (changes: Partial<CharactersDraft>) => void };

function PlayersFields({ draft, hint, update }: FieldsProps & { hint: string | undefined }) {
  const counts = Array.from({ length: MAX_PLAYERS }, (_, index) => index + 1);
  return (
    <fieldset className="scenario-players">
      <legend>추천 인원</legend>
      <p className="ui-field__hint">추천일 뿐 테이블의 정원을 막지 않습니다. 프리젠만 고를 수 있게 하면 프리젠이 최소 인원만큼 있어야 합니다.</p>
      <div className="scenario-players__row">
        <SelectField label="최소" value={draft.minPlayers} onChange={(event) => update({ minPlayers: Number(event.target.value) })}>
          {counts.map((count) => (
            <option key={count} value={count}>
              {count}명
            </option>
          ))}
        </SelectField>
        <SelectField label="최대" value={draft.maxPlayers} onChange={(event) => update({ maxPlayers: Number(event.target.value) })} error={hint}>
          {counts.map((count) => (
            <option key={count} value={count}>
              {count}명
            </option>
          ))}
        </SelectField>
      </div>
    </fieldset>
  );
}

function ModesFields({ draft, rules, hint, update }: FieldsProps & { rules: Ruleset | null; hint: string | undefined }) {
  const warnings = modeWarnings(draft.modes, rules);
  return (
    <fieldset className="scenario-choices">
      <legend>캐릭터를 얻는 방식</legend>
      <p className="ui-field__hint">테이블을 여는 사람이 이 가운데서 더 좁힐 수 있습니다.</p>
      {CHARACTER_MODES.map((mode) => (
        <Checkbox
          key={mode}
          label={characterModeLabel(mode)}
          description={MODE_HINTS[mode]}
          checked={draft.modes.includes(mode)}
          onChange={() => update({ modes: toggleMode(draft.modes, mode) })}
        />
      ))}
      {draft.modes.includes('rolled') ? (
        <Checkbox
          label="방장이 다시 굴리게 해 줄 수 있음"
          checked={draft.reroll}
          onChange={(event) => update({ reroll: event.target.checked })}
        />
      ) : null}
      {hint ? <p className="ui-field__error">{hint}</p> : null}
      {warnings.map((warning) => (
        <p key={warning} className="ui-field__error">
          {warning}
        </p>
      ))}
    </fieldset>
  );
}

function HpFields({ draft, rules, hints, update }: FieldsProps & { rules: Ruleset | null; hints: Record<string, string> }) {
  return (
    <fieldset className="scenario-players">
      <legend>능력치를 정하는 캐릭터의 최대 HP</legend>
      <p className="ui-field__hint">{hpFormulaText(rules)} 둘 다 비우면 게시 점검이 알려 줍니다.</p>
      <div className="scenario-players__row">
        <TextField
          label="기준값"
          inputMode="numeric"
          value={draft.hpBase}
          onChange={(event) => update({ hpBase: event.target.value })}
          error={hints.hp_base}
        />
        <TextField
          label="상한"
          inputMode="numeric"
          value={draft.hpCap}
          onChange={(event) => update({ hpCap: event.target.value })}
          error={hints.hp_cap}
        />
      </div>
    </fieldset>
  );
}
