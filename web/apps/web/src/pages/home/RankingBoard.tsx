// web/apps/web/src/pages/home/RankingBoard.tsx
// 첫 화면의 "이번 주 인기" 판(#985, Stitch 2번의 랭킹). 시나리오, 캐릭터, 세계관을 한 판에 섞어 두 열로 1위부터 10위까지.
// 위의 칩(전체, TRPG, 캐릭터, 스토리)으로 한 종류만 본다. 서버마다 따로 부르고 따로 실패한다(#593):
// 읽은 것만 보이고 아래에 한 줄로 알리며 다시 시도한다. 로그인하지 않아도 보인다.
// 서비스마다의 줄(RankingRows)은 탐색 화면이 쓴다.

import { ChipGroup, type Chip } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { useImageUrl } from '../../hooks/useImageUrl';
import { ScenarioCover } from '../trpg/portraits/ScenarioCover';
import { characterRankingQuery, scenarioRankingQuery, worldRankingQuery } from './queries';
import {
  boardLines,
  lineSubtitle,
  RANKING_KIND_LABELS,
  rankNumber,
  startsText,
  type RankingKind,
  type RankingLine,
} from './rankingBoardView';

type KindChoice = RankingKind | 'all';

const KIND_CHIPS: Chip<KindChoice>[] = [
  { value: 'all', label: '전체' },
  { value: 'trpg', label: RANKING_KIND_LABELS.trpg },
  { value: 'character', label: RANKING_KIND_LABELS.character },
  { value: 'story', label: RANKING_KIND_LABELS.story },
];

export function RankingBoard({ signedIn }: { signedIn: boolean }) {
  const [kind, setKind] = useState<KindChoice>('all');
  const { groups, pending, failed, retry } = useRankingLines(signedIn);
  const lines = boardLines(groups, kind === 'all' ? null : kind);
  return (
    <section className="ranking-board" aria-labelledby="ranking-board-heading">
      <div className="ranking-board__head">
        <h2 id="ranking-board-heading" className="ranking-board__title">
          이번 주 인기
        </h2>
        <span className="ranking-board__basis">최근 7일에 시작한 수</span>
        <ChipGroup label="종류" chips={KIND_CHIPS} selected={kind} onChange={(value) => setKind(value ?? 'all')} />
      </div>
      {pending && lines.length === 0 ? <p className="hint">불러오는 중</p> : null}
      {!pending && lines.length === 0 && !failed ? <p className="hint">이번 주에 시작한 것이 아직 없습니다.</p> : null}
      {lines.length > 0 ? (
        <ol className="ranking-board__list">
          {lines.map((line, index) => (
            <RankingRow key={line.key} line={line} index={index} />
          ))}
        </ol>
      ) : null}
      {failed ? (
        <p className="hint">
          일부를 불러오지 못했습니다.{' '}
          <button type="button" className="ui-button ui-button--quiet" onClick={retry}>
            다시 시도
          </button>
        </p>
      ) : null}
    </section>
  );
}

/** 세 서버의 랭킹을 판의 줄로. 하나라도 읽는 중이면 pending, 하나라도 못 읽었으면 failed */
function useRankingLines(signedIn: boolean) {
  const scenarios = useQuery(scenarioRankingQuery(signedIn));
  const characters = useQuery(characterRankingQuery(signedIn));
  const worlds = useQuery(worldRankingQuery(signedIn));
  const groups: RankingLine[][] = [
    (scenarios.data?.items ?? []).map(({ starts, listing }) => ({
      key: `trpg-${listing.scenario_id}`,
      kind: 'trpg' as const,
      to: `/trpg/scenarios/${listing.scenario_id}`,
      title: listing.title,
      genre: listing.genre,
      starts,
      cover: { scenarioId: listing.scenario_id, imageId: listing.cover_image_id },
    })),
    (characters.data?.items ?? []).map(({ starts, character }) => ({
      key: `character-${character.id}`,
      kind: 'character' as const,
      to: `/chat/characters/${character.id}`,
      title: character.name,
      genre: character.genre,
      starts,
      imageId: character.image_id,
    })),
    (worlds.data?.items ?? []).map(({ starts, world }) => ({
      key: `story-${world.id}`,
      kind: 'story' as const,
      to: `/story/worlds/${world.id}`,
      title: world.name,
      genre: world.genre,
      starts,
      imageId: world.image_id,
    })),
  ];
  return {
    groups,
    pending: scenarios.isPending || characters.isPending || worlds.isPending,
    failed: scenarios.isError || characters.isError || worlds.isError,
    retry: () => {
      for (const query of [scenarios, characters, worlds]) if (query.isError) void query.refetch();
    },
  };
}

function RankingRow({ line, index }: { line: RankingLine; index: number }) {
  return (
    <li>
      <Link to={line.to} className={index < 3 ? 'ranking-board__row ranking-board__row--top' : 'ranking-board__row'}>
        <span className="ranking-board__rank" aria-hidden="true">
          {rankNumber(index)}
        </span>
        <RankingThumb line={line} />
        <span className="ranking-board__name">{line.title}</span>
        <span className={`ranking-board__sub ranking-board__sub--${line.kind}`}>{lineSubtitle(line)}</span>
        <span className="ranking-board__starts">{startsText(line.starts)}</span>
      </Link>
    </li>
  );
}

function RankingThumb({ line }: { line: RankingLine }) {
  if (line.cover) return <ScenarioCover scenarioId={line.cover.scenarioId} coverImageId={line.cover.imageId} className="ranking-board__thumb" />;
  return <PictureThumb imageId={line.imageId} />;
}

function PictureThumb({ imageId }: { imageId: string | null | undefined }) {
  const image = useImageUrl(imageId ?? null);
  return image.url ? <img src={image.url} alt="" className="ranking-board__thumb" /> : <span className="ranking-board__thumb ranking-board__thumb--empty" aria-hidden="true" />;
}
