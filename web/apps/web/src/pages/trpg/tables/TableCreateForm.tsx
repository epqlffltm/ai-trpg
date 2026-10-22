// web/apps/web/src/pages/trpg/tables/TableCreateForm.tsx
// 테이블 만들기(B4)의 입력. 처음에는 스타팅, 정원, 로비에 보이기(와 비밀번호)만 묻고, 나머지는 "자세한 설정"을 열어서 바꾼다.
// 기본값으로 바로 만들 수 있다. 만들면 테이블 방(B6)으로 간다. 방장의 초대 코드는 거기서 보인다.
// 시나리오의 추천 모델을 쓸 수 없으면(422 narration_model) 자세한 설정을 열고 모델 칸에 알린다.

import { Button, Checkbox, ChipGroup, Radio, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { createTable } from '../../../api/tables';
import type { PublicListingDetail } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { useCountdown } from '../../../hooks/useCountdown';
import { PLAYER_COUNTS, playersLabel } from '../labels';
import { AdvancedSettings } from './AdvancedSettings';
import { draftHints, initialDraft, toTableCreate, type CreateDraft } from './createForm';
import { describeCreateProblem } from './tableProblem';
import { useEnterTable } from './useEnterTable';

const CAPACITY_CHIPS = PLAYER_COUNTS.map((count) => ({ value: count, label: count === 1 ? '혼자' : `${count}명` }));

export function TableCreateForm({ listing }: { listing: PublicListingDetail }) {
  const [draft, setDraft] = useState<CreateDraft>(() => initialDraft(listing));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const enterTable = useEnterTable();
  const wait = useCountdown();
  const hints = draftHints(draft);

  function update(changes: Partial<CreateDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const table = await createTable(toTableCreate(draft, listing));
      enterTable(table.id);
    } catch (error) {
      const next = describeCreateProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      setBusy(false);
    }
  }

  return (
    <main className="page page--medium">
      <h1>테이블 만들기</h1>
      <p>
        시나리오 <Link to={`/trpg/scenarios/${listing.scenario_id}`}>{listing.title}</Link>. 만든 사람이 방장으로 앉습니다.
      </p>
      <form onSubmit={submit} noValidate>
        <ProblemNotice problem={problem} />
        {listing.openings.length > 1 ? (
          <fieldset className="choice-list">
            <legend>시작하는 장면</legend>
            {listing.openings.map((opening, index) => (
              <Radio
                key={index}
                name="opening_index"
                label={`${index + 1}번`}
                description={<span className="prose">{opening}</span>}
                checked={draft.openingIndex === index}
                onChange={() => update({ openingIndex: index })}
              />
            ))}
          </fieldset>
        ) : null}
        <div className="ui-field">
          <span className="ui-field__label" id="capacity-label">
            정원(방장 포함)
          </span>
          <ChipGroup<number>
            label="정원"
            chips={CAPACITY_CHIPS}
            selected={draft.capacity}
            onChange={(capacity) => capacity && update({ capacity })}
          />
          <p className="ui-field__hint">시나리오의 추천 인원은 {playersLabel(listing.recommended_players)}입니다. 추천일 뿐 막지 않습니다.</p>
        </div>
        <Checkbox
          label="로비에 보이기"
          description="다른 사람이 로비에서 찾아 들어올 수 있습니다. 만든 뒤에는 바꿀 수 없습니다. 보이지 않으면 초대 코드로만 들어옵니다."
          checked={draft.isPublic}
          onChange={(event) => update({ isPublic: event.target.checked })}
        />
        {draft.isPublic ? (
          <TextField
            label="비밀번호(선택)"
            name="password"
            type="password"
            autoComplete="new-password"
            maxLength={64}
            value={draft.password}
            onChange={(event) => update({ password: event.target.value })}
            error={hints.password}
          />
        ) : null}
        <AdvancedSettings
          listing={listing}
          draft={draft}
          onChange={update}
          hints={hints}
          problem={problem}
        />
        <Button type="submit" busy={busy} disabled={Object.keys(hints).length > 0 || wait.remaining > 0}>
          {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '만들기'}
        </Button>
      </form>
    </main>
  );
}
