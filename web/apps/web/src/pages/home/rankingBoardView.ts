// web/apps/web/src/pages/home/rankingBoardView.ts
// 첫 화면 "이번 주 인기" 판(#985)의 줄을 만드는 순수한 함수. 시나리오, 캐릭터, 세계관의 랭킹을 한 목록으로 섞어
// 이번 주에 시작한 수가 많은 것부터 늘어놓는다. 칩으로 한 종류만 고를 수 있다. 순위 번호는 섞은 목록에서의 차례다.

import { compactCount } from '../../format/count';
import { genreName, isGenreValue } from '../../genres/genres';

export type RankingKind = 'trpg' | 'character' | 'story';

export const RANKING_KIND_LABELS: Record<RankingKind, string> = { trpg: 'TRPG', character: '캐릭터', story: '스토리' };

/** 판의 한 줄. imageId 는 캐릭터·세계관의 대표 그림, cover 는 시나리오의 표지 */
export type RankingLine = {
  key: string;
  kind: RankingKind;
  to: string;
  title: string;
  genre: string | null | undefined;
  starts: number;
  imageId?: string | null | undefined;
  cover?: { scenarioId: string; imageId: string | null | undefined } | undefined;
};

/** 판에 보이는 줄 수 */
export const BOARD_ROWS = 10;

/** 종류마다 읽은 줄을 섞어 시작한 수가 많은 것부터. kind 가 null 이면 모두 */
export function boardLines(groups: RankingLine[][], kind: RankingKind | null, limit = BOARD_ROWS): RankingLine[] {
  return groups
    .flat()
    .filter((line) => kind === null || line.kind === kind)
    .sort((left, right) => right.starts - left.starts)
    .slice(0, limit);
}

/** 줄의 둘째 글: "TRPG · 판타지" */
export function lineSubtitle(line: Pick<RankingLine, 'kind' | 'genre'>): string {
  const genre = line.genre && isGenreValue(line.genre) ? genreName(line.genre) : null;
  return [RANKING_KIND_LABELS[line.kind], genre].filter(Boolean).join(' · ');
}

/** 순위 번호. 두 자리로 쓴다("01") */
export function rankNumber(index: number): string {
  return String(index + 1).padStart(2, '0');
}

/** 오른쪽 끝의 수: "이번 주 12.3K회" */
export function startsText(starts: number): string {
  return `이번 주 ${compactCount(starts)}회`;
}
