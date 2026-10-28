// web/apps/web/src/pages/story/studio/worldLabels.ts
// 세계관 만들기(D7)의 고르는 칸에 보일 이름. 값은 서버의 것이다(asset-server/app/worlds/models.py).

export const REVEAL_LABELS: Record<'shown' | 'silhouette' | 'hidden', string> = { shown: '보임', silhouette: '실루엣(만나기 전까지 ???)', hidden: '숨김(만나기 전까지 없음)' };
export const MAP_LABELS: Record<'shown' | 'hidden' | 'stage', string> = { shown: '보임', hidden: '숨김', stage: '호감도가 정한 단계 이상일 때만' };
export const PANEL_LABELS: Record<'intro' | 'age' | 'gender' | 'affection', string> = { intro: '소개', age: '나이', gender: '성별', affection: '호감도' };

/** 이름이 아직 비었으면 차례로 부른다 */
export function labelOr(name: string, fallback: string): string {
  return name.trim() || fallback;
}
