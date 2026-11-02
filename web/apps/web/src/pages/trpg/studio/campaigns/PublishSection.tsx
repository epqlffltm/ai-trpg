// web/apps/web/src/pages/trpg/studio/campaigns/PublishSection.tsx
// 캠페인의 게시(#481 B). 게시 점검(막는 것과 알릴 것), 게시(변경 내용 500 자), 낸 판의 목록.
// 지금 저장된 편들이 새 판으로 굳고, 편마다 그때의 시나리오의 마지막 판 번호가 들어간다.
// 점검에 문제가 있으면 게시를 끈다(서버도 409 로 막는다). 알릴 것은 게시를 막지 않는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import type { CampaignPublishCheck } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { formatDate } from '../../../../format/dateTime';
import { NOTE_MAX } from '../scenarios/PublishTab';
import { campaignCheckQuery, campaignVersionsQuery } from './campaignQueries';
import { problemText, warningText } from './checkLines';
import { usePublishCampaign } from './useCampaignActions';

export function PublishSection({ campaignId }: { campaignId: string }) {
  const check = useQuery(campaignCheckQuery(campaignId));
  return (
    <section className="page-section" aria-labelledby="campaign-publish-heading">
      <h2 id="campaign-publish-heading">게시</h2>
      {check.isPending ? <p aria-busy="true">확인하는 중</p> : null}
      {check.isError ? (
        <Notice tone="error">
          게시 점검을 하지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void check.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {check.data ? <CheckLines check={check.data} /> : null}
      <PublishForm campaignId={campaignId} ready={check.data?.ready !== false} />
      <Versions campaignId={campaignId} />
    </section>
  );
}

function CheckLines({ check }: { check: CampaignPublishCheck }) {
  return (
    <>
      {check.ready ? <p>지금 게시할 수 있습니다.</p> : <p>게시하려면 고칠 것이 {check.problems.length}개 있습니다.</p>}
      {check.problems.length > 0 ? (
        <ul className="plain-list scenario-check__list" aria-label="고칠 것">
          {check.problems.map((name) => (
            <li key={name} className="scenario-check__item">
              {problemText(name)}
            </li>
          ))}
        </ul>
      ) : null}
      {check.warnings.length > 0 ? (
        <ul className="plain-list scenario-check__list" aria-label="알릴 것">
          {check.warnings.map((name) => (
            <li key={name} className="scenario-check__item hint">
              {warningText(name)}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function PublishForm({ campaignId, ready }: { campaignId: string; ready: boolean }) {
  const publishing = usePublishCampaign(campaignId);
  const [note, setNote] = useState('');
  const [published, setPublished] = useState<number | null>(null);
  const blocked = !ready || note.length > NOTE_MAX;

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
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="캠페인 게시">
      <p className="hint">
        지금 저장된 편들이 새 판으로 굳습니다. 편마다 그 시나리오를 게시한 마지막 판이 들어갑니다. 이미 시작한 플레이는 그 플레이의 판을 그대로
        씁니다.
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
        {!ready ? <span className="hint">게시 점검의 문제를 먼저 고쳐 주세요.</span> : null}
      </div>
    </form>
  );
}

function Versions({ campaignId }: { campaignId: string }) {
  const versions = useQuery(campaignVersionsQuery(campaignId));
  return (
    <>
      <h3>낸 판</h3>
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
    </>
  );
}
