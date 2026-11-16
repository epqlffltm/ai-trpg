// web/apps/web/src/components/AchievementProgress.tsx
// 소개 화면 셋(시나리오, 캐릭터, 세계관)의 업적 칸 위쪽(Stitch 5·33번, 스팀의 업적 창을 본뜸).
//   - AchievementProgress: "내가 받은 업적 3 / 12개"와 채워지는 막대, 오른쪽에 몇 %. 로그인했을 때만 둔다
//   - AchievementFilter: 전체 · 받음(n) · 남음(n) 칩. 고른 것은 useAchievementFilter 가 들고 있다
//   - RareChip: 받은 사람이 적은(10% 미만) 업적의 "희귀" 표시
// 업적을 주는 것은 각 서버의 엔진이다. 여기서는 받은 때(earned_at)만 읽는다.

import { ChipGroup, type Chip } from '@ai-trpg/ui';
import { useState } from 'react';

type Earnable = { earned_at?: string | null | undefined };

export type AchievementShow = 'all' | 'earned' | 'left';

/** 받은 수와 전체 수 */
export function earnedCount(items: Earnable[]): number {
  return items.filter((item) => item.earned_at).length;
}

/** 받은 비율(0~100, 정수). 업적이 없으면 0 */
export function earnedPercent(earned: number, total: number): number {
  return total > 0 ? Math.round((earned / total) * 100) : 0;
}

/** 희귀: 플레이한 사람이 있고, 받은 사람이 그 10% 미만 */
export function isRare(earned: number, players: number | null | undefined): boolean {
  return Boolean(players && players > 0 && earned / players < 0.1);
}

/** 고른 칩에 맞는 업적만 */
export function filterAchievements<T extends Earnable>(items: T[], show: AchievementShow): T[] {
  if (show === 'earned') return items.filter((item) => item.earned_at);
  if (show === 'left') return items.filter((item) => !item.earned_at);
  return items;
}

export function useAchievementFilter() {
  return useState<AchievementShow>('all');
}

export function AchievementProgress({ items, line }: { items: Earnable[]; line: string }) {
  const earned = earnedCount(items);
  const percent = earnedPercent(earned, items.length);
  return (
    <div className="achievement-progress">
      <p className="achievement-progress__line">{line}</p>
      <span className="achievement-progress__percent" aria-hidden="true">
        {percent}%
      </span>
      <span className="achievement-progress__bar" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </span>
    </div>
  );
}

type FilterProps = { items: Earnable[]; show: AchievementShow; onChange: (show: AchievementShow) => void };

export function AchievementFilter({ items, show, onChange }: FilterProps) {
  const earned = earnedCount(items);
  const chips: Chip<AchievementShow>[] = [
    { value: 'all', label: '전체' },
    { value: 'earned', label: `받음 (${earned})` },
    { value: 'left', label: `남음 (${items.length - earned})` },
  ];
  return <ChipGroup label="업적 거르기" chips={chips} selected={show} onChange={(value) => onChange(value ?? 'all')} />;
}

export function RareChip() {
  return <span className="achievement-item__rare">희귀</span>;
}
