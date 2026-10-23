// web/apps/web/src/pages/trpg/studio/scenarios/PublishTab.tsx
// 시나리오의 게시 탭(B9). 지금 저장된 내용을 새 판으로 굳히고(변경 내용 500 자), 낸 판의 목록을 보인다.
// 게시 점검에 문제가 있으면 게시를 끈다(서버도 409 로 막는다). 저장하지 않은 탭의 고침은 판에 들어가지 않는다.
// 판을 공개하는 것(소개 페이지와 공개)은 다음 화면에서 더한다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { formatDate } from '../../../../format/dateTime';
import { publishCheckQuery, versionsQuery } from './scenarioQueries';
import { usePublish } from './usePublish';

export const NOTE_MAX = 500;

export function PublishTab({ scenario }: { scenario: ScenarioDetail }) {
  const check = useQuery(publishCheckQuery(scenario.id));
  const publishing = usePublish(scenario.id);
  const [note, setNote] = useState('');
  const [published, setPublished] = useState<number | null>(null);
  const blocked = check.data?.ready === false || note.length > NOTE_MAX;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    setPublished(null);
    const version = await publishing.publish(note);
    if (!version) return;
    setPublished(version.number);
    setNote('');
  }

  return (
    <>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="게시">
        <p className="hint">
          지금 저장된 내용이 새 판으로 굳습니다. 저장하지 않은 고침은 들어가지 않습니다. 이미 연 테이블은 그 테이블의 판을 그대로 씁니다.
        </p>
        {published !== null ? <Notice>{published}판을 게시했습니다.</Notice> : null}
        <ProblemNotice problem={publishing.problem} />
        <TextAreaField
          label="바뀐 것(선택)"
          name="note"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          error={note.length > NOTE_MAX ? `${NOTE_MAX}자까지입니다.` : undefined}
          hint={`${note.length} / ${NOTE_MAX}자. 아래 판의 목록에 남습니다.`}
        />
        <div className="form-actions">
          <Button type="submit" busy={publishing.busy} disabled={blocked}>
            게시
          </Button>
          {check.data?.ready === false ? <span className="hint">게시 점검의 문제를 먼저 고쳐 주세요.</span> : null}
        </div>
      </form>
      <Versions scenarioId={scenario.id} />
    </>
  );
}

function Versions({ scenarioId }: { scenarioId: string }) {
  const versions = useQuery(versionsQuery(scenarioId));
  return (
    <section className="page-section" aria-labelledby="scenario-versions-heading">
      <h2 id="scenario-versions-heading">낸 판</h2>
      <p className="hint">판을 공개해야 다른 사람이 테이블을 열 수 있습니다. 공개하는 화면은 준비 중입니다.</p>
      {versions.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {versions.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void versions.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {versions.isSuccess && versions.data.length === 0 ? <p>아직 낸 판이 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="판">
        {(versions.data ?? []).map((version) => (
          <li key={version.id} className="studio-list__item">
            <strong>{version.number}판</strong> <span className="hint">{formatDate(version.created_at)}</span>
            {version.note ? <p className="studio-list__description">{version.note}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
