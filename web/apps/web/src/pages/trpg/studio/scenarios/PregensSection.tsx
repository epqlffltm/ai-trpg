// web/apps/web/src/pages/trpg/studio/scenarios/PregensSection.tsx
// 시나리오의 프리젠(B9, 캐릭터 탭의 아래). 8 개까지. 더하기와 고치기는 창에서, 지우기는 한 번 더 묻는다.
// 창에서 저장하면 프리젠 목록을 통째로 바로 보낸다(탭의 저장과 따로다). 소지품과 돈은 물건·돈의 탭이 고친다.

import { Button, Dialog, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { Ruleset, ScenarioDetail, ScenarioPregen } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import {
  MAX_PREGENS,
  otherNames,
  PREGEN_DESCRIPTION_MAX,
  PREGEN_NAME_MAX,
  pregenDraft,
  pregenExtras,
  pregenHints,
  toPregen,
  toPregensBody,
  withoutPregen,
  withPregen,
  type PregenDraft,
} from './pregenForm';
import { sheetFieldHints, sheetLine } from './sheetForm';
import { SheetFields } from './SheetFields';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null };

export function PregensSection({ scenario, rules }: Props) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const removing = useScenarioSave(scenario.id);
  const pregens = scenario.pregens;
  const full = pregens.length >= MAX_PREGENS;

  async function remove(at: number): Promise<boolean> {
    return (await removing.save(toPregensBody(withoutPregen(pregens, at)))) !== null;
  }

  return (
    <section className="page-section" aria-labelledby="pregens-heading">
      <h2 id="pregens-heading">
        프리젠{' '}
        <span className="hint">
          ({pregens.length} / {MAX_PREGENS})
        </span>
      </h2>
      <p className="hint">미리 만들어 둔 캐릭터입니다. "준비된 캐릭터(프리젠)" 방식에서 고릅니다. 창에서 저장하면 바로 저장됩니다.</p>
      <p>
        <Button variant="secondary" disabled={full} onClick={() => setEditing('new')}>
          프리젠 더하기
        </Button>
      </p>
      {pregens.length === 0 ? <p className="hint">아직 프리젠이 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="프리젠">
        {pregens.map((pregen, at) => (
          <li key={pregen.name} className="studio-list__item studio-item">
            <div>
              <strong>{pregen.name}</strong>
              <div className="studio-list__description">
                <span className="hint">{sheetLine(pregen.sheet, rules) ?? '시트 없음'}</span>
                {pregenExtras(pregen) ? <span className="hint"> · {pregenExtras(pregen)}</span> : null}
              </div>
            </div>
            <span className="action-chips">
              <Button variant="quiet" aria-label={`${pregen.name} 고치기`} onClick={() => setEditing(at)}>
                고치기
              </Button>
              <ConfirmButton
                label="지우기"
                ariaLabel={`${pregen.name} 지우기`}
                title="프리젠 지우기"
                confirm="지우기"
                busy={removing.busy}
                problem={removing.problem}
                onConfirm={() => remove(at)}
              >
                <p>「{pregen.name}」</p>
                <p>지우면 되돌릴 수 없습니다. 이미 게시한 판의 프리젠은 그대로입니다.</p>
              </ConfirmButton>
            </span>
          </li>
        ))}
      </ul>
      <Dialog title={editing === 'new' ? '프리젠 더하기' : '프리젠 고치기'} open={editing !== null} onClose={close}>
        {editing !== null ? (
          <PregenForm scenario={scenario} rules={rules} at={editing === 'new' ? null : editing} done={close} />
        ) : null}
      </Dialog>
    </section>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; at: number | null; done: () => void };

function PregenForm({ scenario, rules, at, done }: FormProps) {
  const original: ScenarioPregen | null = at === null ? null : (scenario.pregens[at] ?? null);
  const [draft, setDraft] = useState<PregenDraft>(() => pregenDraft(original, rules));
  const saving = useScenarioSave(scenario.id);
  const hints = pregenHints(draft, rules, otherNames(scenario.pregens, at));
  const blocked = Object.keys(hints).length > 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    const pregens = withPregen(scenario.pregens, at, toPregen(draft, rules, original));
    if (await saving.save(toPregensBody(pregens))) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="프리젠">
      <ProblemNotice problem={saving.problem} />
      <TextField
        label="이름"
        name="name"
        maxLength={PREGEN_NAME_MAX}
        value={draft.name}
        onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
        error={draft.name === '' ? undefined : hints.name}
      />
      <TextAreaField
        label="설명(선택)"
        name="description"
        rows={4}
        maxLength={PREGEN_DESCRIPTION_MAX}
        value={draft.description}
        onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
        error={hints.description}
        hint={`${draft.description.length} / ${PREGEN_DESCRIPTION_MAX}자. 고르는 사람이 보는 소개입니다.`}
      />
      {rules && draft.sheet ? (
        <SheetFields
          legend="시트"
          rules={rules}
          draft={draft.sheet}
          hints={sheetFieldHints(hints)}
          onChange={(sheet) => setDraft((current) => ({ ...current, sheet }))}
        />
      ) : (
        <p className="hint">룰북을 고르면 시트(능력치와 최대 HP)를 적을 수 있습니다.</p>
      )}
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          {at === null ? '더하기' : '저장'}
        </Button>
      </div>
    </form>
  );
}

