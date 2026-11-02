// web/apps/web/src/pages/trpg/campaigns/runView.ts
// 캠페인의 플레이(#481 B)를 보일 글과 다음에 할 일로 바꾼다. 순수한 함수다.
//
// 다음에 할 일(테이블 방에서 본 그 편의 테이블이 끝난 뒤):
//   - open: 방장이고 다음 편의 테이블이 아직 없다. 다음 편을 연다
//   - wait: 방장이 아니고 다음 편의 테이블이 아직 없다. 방장이 열기를 기다린다
//   - enter: 다음 편의 테이블이 있다. 방장은 이미 앉아 있어 그리 가고, 다른 사람은 들어간다(이미 앉았으면 그리 간다)
//   - finished: 마지막 편이다. 캠페인을 마쳤다
// 끝나지 않은 편이면 할 일이 없다(null).

import type { CampaignCarry, CampaignRun, CampaignRunEpisode, CampaignRunSummary } from '../../../api/types';

export type NextStep = { kind: 'open' } | { kind: 'wait' } | { kind: 'enter'; tableId: string } | { kind: 'finished' };

/** "2편: 지하 묘지 (2/3)". position 은 0 이 1편이다 */
export function episodeLabel(position: number, title: string, count: number): string {
  return `${position + 1}편: ${title} (${position + 1}/${count})`;
}

/** 그 테이블이 플레이의 몇 번째 편인가. 플레이에 없는 테이블이면 null */
export function episodeOfTable(run: CampaignRun, tableId: string): CampaignRunEpisode | null {
  return run.episodes.find((episode) => episode.table_id === tableId) ?? null;
}

/** 그 편의 테이블이 끝난 뒤에 할 일. 끝나지 않았거나 플레이에 없는 테이블이면 null */
export function nextStep(run: CampaignRun, tableId: string, tableEnded: boolean, myId: string | undefined): NextStep | null {
  const episode = episodeOfTable(run, tableId);
  if (!episode || !tableEnded) return null;
  const next = run.episodes[episode.position + 1];
  if (!next) return { kind: 'finished' };
  if (next.table_id) return { kind: 'enter', tableId: next.table_id };
  return run.host_id === myId ? { kind: 'open' } : { kind: 'wait' };
}

/** 넘긴 캐릭터의 한 줄. "기사 · 경험치 150 · 최대 HP 15 · 돈 40 · 소지품 2가지" */
export function carryLine(carry: CampaignCarry): string {
  const parts = [carry.character_name, `경험치 ${carry.xp}`, `최대 HP ${carry.max_hp}`, `돈 ${carry.money}`];
  if (carry.points > 0) parts.push(`쓸 점수 ${carry.points}`);
  parts.push(carry.items.length > 0 ? `소지품 ${carry.items.length}가지` : '소지품 없음');
  return parts.join(' · ');
}

/** 목록의 한 줄의 상태. "2편: 지하 묘지 (2/3)" 또는 "마침" */
export function runStateLabel(run: CampaignRunSummary): string {
  if (run.status === 'ended') return '마침';
  return episodeLabel(run.position, run.episode_title, run.episode_count);
}
