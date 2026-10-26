// web/apps/web/src/pages/trpg/scenario/ScenarioDetail.tsx
// 시나리오 소개(B2)를 그린다. 왼쪽(모바일은 위)에 소개글과 고를 거리, 오른쪽(모바일은 아래)에 요약과 할 일.
// 소개글은 글 그대로 보인다(줄바꿈만 살린다). HTML 로 꾸미는 소개는 asset-server 로 옮길 때 바꾼다(화면 명세 B2).
// 운영자에게는 맨 아래에 제재 칸(E4)이 있다.

import { Link } from 'react-router';
import type { PublicListingDetail } from '../../../api/types';
import { isOperator } from '../../../auth/roles';
import { useSession } from '../../../auth/useSession';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { ScenarioOperatorPanel } from '../../operator/ScenarioOperatorPanel';
import { tagSearchPath } from '../browse/filters';
import { characterModeLabel } from '../labels';
import { PregenList } from './PregenList';
import { ScenarioSidePanel } from './ScenarioSidePanel';

export function ScenarioDetail({ listing }: { listing: PublicListingDetail }) {
  const nameOf = usePublicNames([[listing.creator_id]]);
  const creator = nameOf(listing.creator_id);
  const operator = isOperator(useSession());
  return (
    <main className="page scenario">
      <header className="scenario__head">
        <h1>{listing.title}</h1>
        {listing.tagline ? <p className="scenario__tagline">{listing.tagline}</p> : null}
        {creator ? <p className="scenario__byline">만든 사람 {creator}</p> : null}
      </header>
      <div className="scenario__body">
        <div className="scenario__main">
          <section aria-labelledby="scenario-description">
            <h2 id="scenario-description">소개</h2>
            <p className="prose">{listing.description || '소개글이 없습니다.'}</p>
          </section>
          {listing.tags.length > 0 ? <TagLinks tags={listing.tags} /> : null}
          {listing.openings.length > 0 ? <Openings openings={listing.openings} /> : null}
          <CharacterModes listing={listing} />
          {listing.version_note ? (
            <section aria-labelledby="scenario-version">
              <h2 id="scenario-version">{listing.version}판에서 바뀐 것</h2>
              <p className="prose">{listing.version_note}</p>
            </section>
          ) : null}
        </div>
        <ScenarioSidePanel listing={listing} />
      </div>
      {operator ? <ScenarioOperatorPanel listing={listing} creatorName={creator} /> : null}
    </main>
  );
}

function TagLinks({ tags }: { tags: string[] }) {
  return (
    <ul className="tag-links" aria-label="태그">
      {tags.map((tag) => (
        <li key={tag}>
          <Link to={tagSearchPath(tag)}>#{tag}</Link>
        </li>
      ))}
    </ul>
  );
}

/** 스타팅. 테이블을 만들 때(B4) 이 차례의 순번으로 고른다 */
function Openings({ openings }: { openings: string[] }) {
  return (
    <section aria-labelledby="scenario-openings">
      <h2 id="scenario-openings">시작하는 장면</h2>
      <p className="hint">테이블을 만들 때 하나를 고릅니다.</p>
      <ol className="openings">
        {openings.map((opening, index) => (
          <li key={index} className="prose">
            {opening}
          </li>
        ))}
      </ol>
    </section>
  );
}

function CharacterModes({ listing }: { listing: PublicListingDetail }) {
  return (
    <section aria-labelledby="scenario-characters">
      <h2 id="scenario-characters">캐릭터</h2>
      <p>
        이 시나리오에서 캐릭터를 얻는 방식: {listing.character_modes.map(characterModeLabel).join(', ') || '정해지지 않음'}
      </p>
      {listing.pregens.length > 0 ? <PregenList pregens={listing.pregens} abilities={listing.abilities} /> : null}
    </section>
  );
}
