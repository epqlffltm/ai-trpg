// web/apps/web/src/pages/chat/studio/lorebooks/entriesForm.ts
// 로어북 항목의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/lorebooks/schemas.py 의 LoreEntry).
//
//   - 항목은 200 개까지. 이름(100자)과 내용(500자)은 꼭 있어야 하고 둘 다 모델에 간다
//   - 키워드는 쉼표로 나눠 5 개까지, 하나에 30자. 대소문자만 다른 것도 겹친 것이다
//   - 늘 넣기(constant)면 대화마다 모델에 간다. 아니면 키워드가 최근 대화에 나올 때 간다
//   - 종류는 보이기만 한다(chat 은 지금 종류로 다르게 다루지 않는다)
//   - id 는 화면이 붙인다(lore-xxxxxxxx). 이미 있는 것은 바꾸지 않는다
//   - 저장은 항목의 목록을 통째로 보낸다

import type { AssetLoreEntry, AssetLoreKind, AssetLorebookDetail, AssetLorebookUpdate } from '../../../../api/types';

export const ENTRIES_MAX = 200;
export const ENTRY_NAME_MAX = 100;
export const ENTRY_CONTENT_MAX = 500;
export const KEYWORDS_MAX = 5;
export const KEYWORD_MAX = 30;

export const LORE_KINDS: Record<AssetLoreKind, string> = {
  person: '인물',
  place: '장소',
  item: '물건',
  faction: '세력',
  species: '종족',
  legend: '전설',
  event: '사건',
  other: '기타',
};

export type EntryDraft = {
  id: string;
  name: string;
  kind: AssetLoreKind;
  keywords: string;
  content: string;
  constant: boolean;
};

export function entryDrafts(lorebook: AssetLorebookDetail): EntryDraft[] {
  return lorebook.entries.map((entry) => ({
    id: entry.id,
    name: entry.name,
    kind: entry.kind,
    keywords: entry.keywords.join(', '),
    content: entry.content,
    constant: entry.constant,
  }));
}

export function addEntry(entries: EntryDraft[], id: string): EntryDraft[] {
  if (entries.length >= ENTRIES_MAX) return entries;
  return [...entries, { id, name: '', kind: 'other', keywords: '', content: '', constant: false }];
}

export function changeEntry(entries: EntryDraft[], id: string, changes: Partial<Omit<EntryDraft, 'id'>>): EntryDraft[] {
  return entries.map((entry) => (entry.id === id ? { ...entry, ...changes } : entry));
}

export function removeEntry(entries: EntryDraft[], id: string): EntryDraft[] {
  return entries.filter((entry) => entry.id !== id);
}

/** 쉼표로 나눈 키워드. 앞뒤 빈칸을 떼고 빈 것은 뺀다. 겹친 것은 남긴다(알려서 고치게 한다) */
export function splitKeywords(text: string): string[] {
  return text
    .split(',')
    .map((word) => word.trim())
    .filter((word) => word !== '');
}

function keywordsHint(keywords: string[]): string | undefined {
  if (keywords.length > KEYWORDS_MAX) return `키워드는 ${KEYWORDS_MAX}개까지입니다.`;
  if (keywords.some((word) => word.length > KEYWORD_MAX)) return `키워드 하나는 ${KEYWORD_MAX}자까지입니다.`;
  const folded = keywords.map((word) => word.toLocaleLowerCase());
  return new Set(folded).size === folded.length ? undefined : '같은 키워드가 두 번 있습니다.';
}

export type EntryHints = Record<string, Partial<Record<'name' | 'content' | 'keywords', string>>>;

/** 항목마다(id → 칸 → 글)의 문제 */
export function entriesHints(entries: EntryDraft[]): EntryHints {
  const hints: EntryHints = {};
  for (const entry of entries) {
    const found: EntryHints[string] = {};
    const name = entry.name.trim();
    if (name === '') found.name = '이름을 적어 주세요.';
    else if (name.length > ENTRY_NAME_MAX) found.name = `이름은 ${ENTRY_NAME_MAX}자까지입니다.`;
    const content = entry.content.trim();
    if (content === '') found.content = '내용을 적어 주세요.';
    else if (content.length > ENTRY_CONTENT_MAX) found.content = `내용은 ${ENTRY_CONTENT_MAX}자까지입니다.`;
    const keywords = keywordsHint(splitKeywords(entry.keywords));
    if (keywords) found.keywords = keywords;
    if (Object.keys(found).length > 0) hints[entry.id] = found;
  }
  return hints;
}

function toEntry(entry: EntryDraft): AssetLoreEntry {
  return {
    id: entry.id,
    name: entry.name.trim(),
    kind: entry.kind,
    keywords: splitKeywords(entry.keywords),
    content: entry.content.trim(),
    constant: entry.constant,
  };
}

/** 항목의 목록만 보낸다. 힌트가 없을 때만 부른다 */
export function toEntriesBody(entries: EntryDraft[]): AssetLorebookUpdate {
  return { entries: entries.map(toEntry) };
}
