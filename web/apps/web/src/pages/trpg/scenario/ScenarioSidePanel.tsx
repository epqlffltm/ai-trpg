// web/apps/web/src/pages/trpg/scenario/ScenarioSidePanel.tsx
// 소개(B2)의 요약과 할 일. 등급, 장르, 추천 인원, 판, 공개한 날, 추천 서술 모델, "테이블 만들기", "열린 테이블 보기".
// 테이블 만들기(B4)와 로비(B3)는 아직 "준비 중"이다. 주소만 먼저 정해 시나리오를 들고 간다.
// 로그인하지 않았으면 테이블 만들기는 로그인으로 보내고, 마치면 이 화면으로 돌아온다.

import { Link, useLocation } from 'react-router';
import type { PublicListingDetail } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { formatDate } from '../../../format/dateTime';
import { genreLabel, playersLabel } from '../labels';
import { RecommendedModel } from './RecommendedModel';

export function ScenarioSidePanel({ listing }: { listing: PublicListingDetail }) {
  return (
    <aside className="scenario__side" aria-label="요약">
      <dl className="facts">
        <dt>등급</dt>
        <dd>{listing.rating === 'adult' ? '성인' : '전체이용가'}</dd>
        <dt>장르</dt>
        <dd>{listing.genre ? genreLabel(listing.genre) : '없음'}</dd>
        <dt>추천 인원</dt>
        <dd>{playersLabel(listing.recommended_players)}</dd>
        <dt>판</dt>
        <dd>{listing.version}판</dd>
        <dt>공개한 날</dt>
        <dd>{formatDate(listing.published_at)}</dd>
        {listing.references_allowed ? (
          <>
            <dt>참고 자료</dt>
            <dd>방장이 켤 수 있음</dd>
          </>
        ) : null}
        <RecommendedModel slug={listing.recommended_narration_model} />
      </dl>
      <ScenarioActions scenarioId={listing.scenario_id} />
    </aside>
  );
}

function ScenarioActions({ scenarioId }: { scenarioId: string }) {
  const signedIn = useSession() !== null;
  const location = useLocation();
  const query = new URLSearchParams({ scenario_id: scenarioId }).toString();
  return (
    <div className="scenario__actions">
      {signedIn ? (
        <Link className="ui-button ui-button--primary" to={`/trpg/tables/new?${query}`}>
          테이블 만들기
        </Link>
      ) : (
        <Link className="ui-button ui-button--primary" to="/login" state={{ from: location.pathname }}>
          로그인하고 테이블 만들기
        </Link>
      )}
      <Link className="ui-button ui-button--secondary" to={`/trpg/lobby?${query}`}>
        열린 테이블 보기
      </Link>
    </div>
  );
}
