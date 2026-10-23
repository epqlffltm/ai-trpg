// web/apps/web/src/pages/trpg/studio/scenarios/PublishTab.tsx
// 시나리오의 게시 탭(B9). 지금 저장된 내용을 새 판으로 굳히고(변경 내용 500 자), 낸 판의 목록에서 판 하나를 공개한다.
// 게시 점검에 문제가 있으면 게시를 끈다(서버도 409 로 막는다). 저장하지 않은 탭의 고침은 판에 들어가지 않는다.
// 공개는 소개 탭의 한줄소개와 장르가 있어야 한다. 공개는 바로 하고, 공개 내리기는 한 번 더 묻는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import type { ListingDetail, ScenarioDetail, VersionSummary } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { formatDate } from '../../../../format/dateTime';
import { listingProblems, listingProblemText } from './listingForm';
import { listingQuery, publishCheckQuery, versionsQuery } from './scenarioQueries';
import type { ScenarioTab } from './scenarioTabs';
import { usePublication } from './usePublication';
import { usePublish } from './usePublish';

export const NOTE_MAX = 500;

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function PublishTab({ scenario, goTo }: Props) {
  return (
    <>
      <PublishForm scenarioId={scenario.id} />
      <Versions scenarioId={scenario.id} goTo={goTo} />
    </>
  );
}

function PublishForm({ scenarioId }: { scenarioId: string }) {
  const check = useQuery(publishCheckQuery(scenarioId));
  const publishing = usePublish(scenarioId);
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
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="게시">
      <p className="hint">
        지금 저장된 내용이 새 판으로 굳습니다. 저장하지 않은 고침은 들어가지 않습니다. 이미 연 테이블은 그 테이블의 판을 그대로 씁니다.
      </p>
      {published !== null ? <Notice>{published}판을 게시했습니다. 공개하려면 아래 낸 판에서 고르세요.</Notice> : null}
      <ProblemNotice problem={publishing.problem} />
      <TextAreaField
        label="바뀐 것(선택)"
        name="note"
        rows={3}
        maxLength={NOTE_MAX}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        error={note.length > NOTE_MAX ? `${NOTE_MAX}자까지입니다.` : undefined}
        hint={`${note.length} / ${NOTE_MAX}자. 아래 판의 목록에 남고, 공개하면 소개에도 보입니다.`}
      />
      <div className="form-actions">
        <Button type="submit" busy={publishing.busy} disabled={blocked}>
          게시
        </Button>
        {check.data?.ready === false ? <span className="hint">게시 점검의 문제를 먼저 고쳐 주세요.</span> : null}
      </div>
    </form>
  );
}

function Versions({ scenarioId, goTo }: { scenarioId: string; goTo: (tab: ScenarioTab) => void }) {
  const versions = useQuery(versionsQuery(scenarioId));
  const listing = useQuery(listingQuery(scenarioId));
  const publication = usePublication(scenarioId);

  return (
    <section className="page-section" aria-labelledby="scenario-versions-heading">
      <h2 id="scenario-versions-heading">낸 판</h2>
      {listing.data ? <PublicationNote listing={listing.data} goTo={goTo} /> : null}
      <ProblemNotice problem={publication.problem} />
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
          <li key={version.id} className="studio-list__item studio-item">
            <VersionLine version={version} published={listing.data?.version === version.number} />
            {listing.data ? <VersionAction version={version} listing={listing.data} publication={publication} /> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 공개의 지금 상태. 소개가 조건을 갖추지 못했으면 까닭과 소개 탭으로 가는 단추 */
function PublicationNote({ listing, goTo }: { listing: ListingDetail; goTo: (tab: ScenarioTab) => void }) {
  const problems = listingProblems(listing);
  const state =
    listing.version === null
      ? '공개한 판이 없습니다. 판을 공개해야 다른 사람이 소개를 보고 테이블을 열 수 있습니다.'
      : `${listing.version}판을 공개 중입니다. 다른 판을 공개하면 그 판으로 바뀝니다.`;
  return (
    <>
      <p className="hint">{state}</p>
      {problems.length > 0 ? (
        <Notice>
          공개하려면 소개를 먼저 채워 주세요. {problems.map(listingProblemText).join(' ')}{' '}
          <Button variant="quiet" onClick={() => goTo('listing')}>
            소개 탭으로
          </Button>
        </Notice>
      ) : null}
    </>
  );
}

function VersionLine({ version, published }: { version: VersionSummary; published: boolean }) {
  return (
    <div>
      <strong>{version.number}판</strong> <span className="hint">{formatDate(version.created_at)}</span>
      {published ? <span className="version-published">공개 중</span> : null}
      {version.note ? <p className="studio-list__description">{version.note}</p> : null}
    </div>
  );
}

type ActionProps = { version: VersionSummary; listing: ListingDetail; publication: ReturnType<typeof usePublication> };

function VersionAction({ version, listing, publication }: ActionProps) {
  if (listing.version === version.number) {
    return (
      <ConfirmButton
        label="공개 내리기"
        ariaLabel={`${version.number}판 공개 내리기`}
        title="공개를 내릴까요?"
        confirm="공개 내리기"
        busy={publication.busy}
        problem={publication.problem}
        onConfirm={async () => (await publication.publish(null)) !== null}
      >
        <p>공개 목록과 소개에서 빠지고, 새 테이블을 열 수 없게 됩니다. 이미 연 테이블은 그대로 이어집니다. 소개 탭의 글과 낸 판은 남습니다.</p>
      </ConfirmButton>
    );
  }
  return (
    <Button
      variant="quiet"
      aria-label={`${version.number}판 공개`}
      disabled={publication.busy || listingProblems(listing).length > 0}
      onClick={() => void publication.publish(version.number)}
    >
      공개
    </Button>
  );
}
