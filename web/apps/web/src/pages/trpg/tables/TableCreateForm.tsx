// web/apps/web/src/pages/trpg/tables/TableCreateForm.tsx
// 테이블 만들기(B4)의 입력. 처음에는 스타팅, 정원, 로비에 보이기(와 비밀번호)만 묻고, 나머지는 "자세한 설정"을 열어서 바꾼다.
// 기본값으로 바로 만들 수 있다. 만들면 테이블 방(B6)으로 간다. 방장의 초대 코드는 거기서 보인다.
// 시나리오의 추천 모델을 쓸 수 없으면(422 narration_model) 자세한 설정을 열고 모델 칸에 알린다.
// 모양은 Stitch 14번: 번호가 붙은 칸(1 시나리오와 시작 장면, 2 기본 설정, 3 규칙과 서술), 넓은 화면에서는 오른쪽에 요약과 "만들기"가 붙어 따라온다.
// 요약(CreateSummary)은 지금 고른 값을 다시 보일 뿐이다. 값을 정하는 것은 서버다.

import { Button, Checkbox, ChipGroup, Radio, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent, type ReactNode } from 'react';
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
    <main className="page table-create">
      <h1>테이블 만들기</h1>
      <p className="hint">만든 사람이 방장으로 앉습니다.</p>
      <form className="table-create__form" onSubmit={submit} noValidate>
        <div className="table-create__main">
          <ProblemNotice problem={problem} />
          <CreateStep number={1} title="시나리오와 시작 장면">
            <p>
              시나리오 <Link to={`/trpg/scenarios/${listing.scenario_id}`}>{listing.title}</Link>
            </p>
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
          </CreateStep>
          <CreateStep number={2} title="기본 설정">
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
          </CreateStep>
          <CreateStep number={3} title="규칙과 서술">
            <AdvancedSettings listing={listing} draft={draft} onChange={update} hints={hints} problem={problem} />
          </CreateStep>
        </div>
        <aside className="table-create__summary" aria-labelledby="create-summary-heading">
          <h2 id="create-summary-heading">요약</h2>
          <CreateSummary listing={listing} draft={draft} />
          <Button type="submit" busy={busy} disabled={Object.keys(hints).length > 0 || wait.remaining > 0}>
            {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '만들기'}
          </Button>
        </aside>
      </form>
    </main>
  );
}

/** 번호가 붙은 칸 하나. 제목은 칸의 이름이다 */
function CreateStep({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  const headingId = `create-step-${number}`;
  return (
    <section className="table-create__step" aria-labelledby={headingId}>
      <h2 id={headingId}>
        <span className="table-create__number" aria-hidden="true">
          {number}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

/** 지금 고른 것의 요약. 시나리오, 정원, 로비에 보이기와 비밀번호 */
function CreateSummary({ listing, draft }: { listing: PublicListingDetail; draft: CreateDraft }) {
  return (
    <dl className="table-create__facts">
      {summaryRows(listing, draft).map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 요약의 줄. 화면을 그리지 않는 순수한 함수 */
export function summaryRows(listing: Pick<PublicListingDetail, 'title'>, draft: Pick<CreateDraft, 'capacity' | 'isPublic' | 'password'>): [string, string][] {
  return [
    ['시나리오', listing.title],
    ['정원', draft.capacity === 1 ? '혼자' : `${draft.capacity}명`],
    ['로비에 보이기', draft.isPublic ? (draft.password ? '보임 · 비밀번호' : '보임') : '보이지 않음(초대 코드로만)'],
  ];
}
