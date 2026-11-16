// web/apps/web/src/pages/trpg/scenario/ScenarioDetail.tsx
// 시나리오 소개(B2)를 그린다. 왼쪽(모바일은 위)에 소개글과 고를 거리, 오른쪽(모바일은 아래)에 요약과 할 일.
// 소개글은 글 그대로 보인다(줄바꿈만 살린다). HTML 로 꾸미는 소개는 asset-server 로 옮길 때 바꾼다(화면 명세 B2).
// 캐릭터 아래에 제작자가 단 업적과 달성률이 있다(ScenarioAchievements). 머리에 관심(하트, #989) 단추가 있다. 운영자에게는 맨 아래에 제재 칸(E4)이 있다.
// 모양은 Stitch 5번(소개 화면 셋의 같은 모양): 머리의 왼쪽(좁으면 위)에 세로로 긴 표지(#1164, 없으면 빈 칸), 오른쪽에 등급·장르·인원 칩,
// 큰 제목, 한 줄 소개, 만든 사람, 관심, 할 일 단추. 아래는 칸마다 카드 한 장(CSS).
// 장르 테마(Stitch 34~44번): main 에 data-genre 를 단다(genres/genreTheme.ts).

import { Link } from 'react-router';
import type { PublicListingDetail } from '../../../api/types';
import { isOperator } from '../../../auth/roles';
import { useSession } from '../../../auth/useSession';
import { CreatorByline } from '../../../components/CreatorByline';
import { HeartButton } from '../../../components/HeartButton';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { ScenarioOperatorPanel } from '../../operator/ScenarioOperatorPanel';
import { tagSearchPath } from '../browse/filters';
import { characterModeLabel, genreLabel, playersLabel } from '../labels';
import { PregenList } from './PregenList';
import { ScenarioAchievements } from './ScenarioAchievements';
import { ScenarioActions, ScenarioSidePanel } from './ScenarioSidePanel';
import { genreTheme } from '../../../genres/genreTheme';
import { ScenarioCover } from '../portraits/ScenarioCover';

export function ScenarioDetail({ listing }: { listing: PublicListingDetail }) {
  // 운영자의 제재 칸이 이름을 함께 보인다. 머리의 "만든 사람"과 같은 읽기라 한 번만 묻는다
  const creator = usePublicNames([[listing.creator_id]])(listing.creator_id);
  const operator = isOperator(useSession());
  return (
    <main className="page scenario" data-genre={genreTheme(listing.genre)}>
      <header className="scenario__head">
        <ScenarioCover scenarioId={listing.scenario_id} coverImageId={listing.cover_image_id} className="scenario__cover" />
        <div className="scenario__info">
          <ul className="intro-chips" aria-label="요약">
            {listing.rating === 'adult' ? <li className="intro-chips__adult">19+</li> : null}
            {listing.genre ? <li>{genreLabel(listing.genre)}</li> : null}
            <li className="intro-chips__players">{playersLabel(listing.recommended_players)}</li>
          </ul>
          <h1>{listing.title}</h1>
          {listing.tagline ? <p className="scenario__tagline">{listing.tagline}</p> : null}
          <CreatorByline creatorId={listing.creator_id} className="scenario__byline" />
          <div className="intro-actions">
            <ScenarioActions scenarioId={listing.scenario_id} />
            <HeartButton kind="scenario" id={listing.scenario_id} count={listing.heart_count} />
          </div>
        </div>
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
          <ScenarioAchievements scenarioId={listing.scenario_id} />
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
      {listing.pregens.length > 0 ? <PregenList scenarioId={listing.scenario_id} pregens={listing.pregens} abilities={listing.abilities} /> : null}
    </section>
  );
}
