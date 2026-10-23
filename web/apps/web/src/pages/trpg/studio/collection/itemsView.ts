// web/apps/web/src/pages/trpg/studio/collection/itemsView.ts
// 묶음에 담긴 것(항목, 몬스터)의 목록을 보일 것. 순수한 함수다.

type Kinded = { kind: string };

/** 담긴 것의 종류마다 몇 개인지. 종류의 차례(labels 의 차례)로, 있는 종류만 */
export function kindCounts<T extends Kinded>(items: T[], labels: Record<string, string>): { kind: string; label: string; count: number }[] {
  return Object.entries(labels)
    .map(([kind, label]) => ({ kind, label, count: items.filter((item) => item.kind === kind).length }))
    .filter((entry) => entry.count > 0);
}

/** 고른 종류만. 고르지 않았으면 전부 */
export function itemsOfKind<T extends Kinded>(items: T[], kind: string | undefined): T[] {
  return kind ? items.filter((item) => item.kind === kind) : items;
}

/** 긴 글의 앞부분. 넘치면 말줄임 */
export function preview(text: string, length = 80): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > length ? `${flat.slice(0, length).trimEnd()}…` : flat;
}
