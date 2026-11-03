// web/apps/web/src/pages/operator/BannersPage.tsx
// 홍보 배너 관리(#994, /operator/banners). 운영자만 열린다(RequireOperator).
// 공개된 작품을 골라 첫 화면의 배너에 걸고 내린다. 시나리오는 게임 서버, 캐릭터와 세계관은 asset 서버에 건다.
// 배너의 그림과 글은 작품의 것 그대로다. 공개를 내리거나 숨긴 작품은 걸린 채로 남지만 보이지 않는다("지금 안 보임").

import { Button, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { createAssetBanner, createScenarioBanner, deleteBanner, fetchAssetBannersForOperator, fetchScenarioBannersForOperator } from '../../api/banners';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { assetRow, bannerHints, canHang, describeBannerProblem, EMPTY_BANNER, scenarioRow, TARGET_LABELS, toAssetBody, toScenarioBody, type BannerDraft, type BannerRow, type BannerTarget } from './bannerForm';

const SCENARIO_KEY = ['trpg', 'admin', 'banners'];
const ASSET_KEY = ['asset', 'admin', 'banners'];

export function BannersPage() {
  return (
    <main className="page page--medium">
      <h1>홍보 배너</h1>
      <p className="hint">첫 화면 위쪽의 넘기는 배너입니다. 서비스마다 차례가 작은 것부터 보입니다(TRPG, chat, story 차례).</p>
      <HangForm />
      <BannerList />
    </main>
  );
}

function HangForm() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<BannerDraft>(EMPTY_BANNER);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const [done, setDone] = useState(false);
  const hints = bannerHints(draft);

  function update(changes: Partial<BannerDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
    setDone(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      if (draft.target === 'scenario') await createScenarioBanner(toScenarioBody(draft));
      else await createAssetBanner(toAssetBody(draft));
      await queryClient.invalidateQueries({ queryKey: draft.target === 'scenario' ? SCENARIO_KEY : ASSET_KEY });
      setDraft(EMPTY_BANNER);
      setDone(true);
    } catch (error) {
      setProblem(describeBannerProblem(error));
    }
    setBusy(false);
  }

  return (
    <form className="page-section" aria-label="배너 걸기" onSubmit={submit} noValidate>
      <h2>배너 걸기</h2>
      <ProblemNotice problem={problem} />
      {done ? <Notice>걸었습니다.</Notice> : null}
      <SelectField label="작품의 종류" name="target" value={draft.target} onChange={(event) => update({ target: event.target.value as BannerTarget })}>
        {Object.entries(TARGET_LABELS).map(([target, label]) => (
          <option key={target} value={target}>
            {label}
          </option>
        ))}
      </SelectField>
      <div className="field-with-hint">
        <TextField label="작품 ID" name="targetId" value={draft.targetId} onChange={(event) => update({ targetId: event.target.value })} error={hints.targetId} />
        <p className="ui-field__hint">소개 화면 주소의 마지막 부분입니다. 공개 목록에 나오는 작품만 걸 수 있습니다.</p>
      </div>
      <div className="field-with-hint">
        <TextField label="차례" name="position" inputMode="numeric" value={draft.position} onChange={(event) => update({ position: event.target.value })} error={hints.position} />
        <p className="ui-field__hint">작은 것이 먼저입니다.</p>
      </div>
      <div className="field-with-hint">
        <TextField label="시작(선택)" name="startsAt" type="datetime-local" value={draft.startsAt} onChange={(event) => update({ startsAt: event.target.value })} />
        <p className="ui-field__hint">비우면 지금부터입니다.</p>
      </div>
      <div className="field-with-hint">
        <TextField label="끝(선택)" name="endsAt" type="datetime-local" value={draft.endsAt} onChange={(event) => update({ endsAt: event.target.value })} error={hints.endsAt} />
        <p className="ui-field__hint">비우면 내릴 때까지입니다.</p>
      </div>
      <Button type="submit" busy={busy} disabled={!canHang(draft)}>
        걸기
      </Button>
    </form>
  );
}

function BannerList() {
  const scenarios = useQuery({ queryKey: SCENARIO_KEY, queryFn: ({ signal }) => fetchScenarioBannersForOperator(signal) });
  const assets = useQuery({ queryKey: ASSET_KEY, queryFn: ({ signal }) => fetchAssetBannersForOperator(signal) });
  const rows = [...(scenarios.data ?? []).map(scenarioRow), ...(assets.data ?? []).map(assetRow)];
  const pending = scenarios.isPending || assets.isPending;

  return (
    <section className="page-section" aria-labelledby="banner-list-heading">
      <h2 id="banner-list-heading">건 배너</h2>
      {scenarios.isError ? <Notice tone="error">시나리오의 배너를 불러오지 못했습니다.</Notice> : null}
      {assets.isError ? <Notice tone="error">캐릭터와 세계관의 배너를 불러오지 못했습니다.</Notice> : null}
      {pending ? <p aria-busy="true">불러오는 중</p> : null}
      {!pending && rows.length === 0 ? <p className="empty-state">건 배너가 없습니다.</p> : null}
      <ul className="plain-list">
        {rows.map((row) => (
          <BannerItem key={`${row.server}:${row.id}`} row={row} />
        ))}
      </ul>
    </section>
  );
}

function BannerItem({ row }: { row: BannerRow }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function remove() {
    setBusy(true);
    setFailed(false);
    try {
      await deleteBanner(row.server, row.id);
      await queryClient.invalidateQueries({ queryKey: row.server === 'game' ? SCENARIO_KEY : ASSET_KEY });
    } catch {
      setFailed(true);
    }
    setBusy(false);
  }

  return (
    <li className="studio-list__item">
      <strong>{row.name}</strong> <span className="badge">{TARGET_LABELS[row.target]}</span> {row.shown ? null : <span className="badge">지금 안 보임</span>}
      <p className="hint">
        차례 {row.position} · {formatDateTime(row.startsAt)}부터 {row.endsAt ? `${formatDateTime(row.endsAt)}까지` : '내릴 때까지'}
      </p>
      {failed ? <p className="ui-field__error">내리지 못했습니다. 다시 시도해 주세요.</p> : null}
      <Button variant="quiet" busy={busy} onClick={() => void remove()} aria-label={`${row.name} 배너 내리기`}>
        내리기
      </Button>
    </li>
  );
}
