// web/apps/web/src/pages/trpg/studio/lorebooks/entryForm.ts
// 로어북 항목 하나의 입력. 순수한 함수다. 한도는 서버의 것이다(trpg-server/app/assets/models.py 의 LORE_*).
//   - 키워드: 서술하는 AI 가 장면에서 이 낱말을 보면 이 항목을 읽는다. 쉼표로 나눠 5 개까지, 하나에 30 자
//   - 지목할 이름: 인물의 진짜 이름으로 맞다고 받는 이름들. 인물에만 뜻이 있어 인물일 때만 보낸다(비우면 항목의 이름)

import type { LoreEntry, LoreEntryCreate, LoreKind } from '../../../../api/types';
import { splitWords, wordsHint } from '../collection/collectionForm';

export const ENTRY_NAME_MAX = 100;
export const ENTRY_CONTENT_MAX = 500;
export const KEYWORDS_MAX = 5;
const KEYWORD_LENGTH = 30;
export const TRUE_NAMES_MAX = 5;
const TRUE_NAME_LENGTH = 50;
export const LOREBOOK_MAX_ENTRIES = 100;

export const LORE_KINDS: Record<LoreKind, string> = {
  person: '인물',
  place: '장소',
  item: '물건',
  faction: '세력',
  species: '종족',
  legend: '전설',
  event: '사건',
  other: '기타',
};

/** 종류마다의 설명. 장소는 맵, 물건은 소지품, 사건은 퀘스트가 된다(시나리오에서 잇는다) */
export const LORE_KIND_HINTS: Partial<Record<LoreKind, string>> = {
  person: '이름 붙은 등장인물입니다. 시나리오에서 NPC 시트를 붙입니다.',
  place: '맵의 장소가 됩니다. 길은 시나리오에서 잇습니다.',
  item: '물건이 됩니다. 값과 효과는 시나리오의 물건 규칙에서 정합니다.',
  event: '퀘스트나 판의 사건이 됩니다.',
  legend: '사실인지 애매한 이야기입니다.',
};

export type EntryDraft = { name: string; kind: LoreKind; keywords: string; content: string; trueNames: string };

export function newEntryDraft(): EntryDraft {
  return { name: '', kind: 'other', keywords: '', content: '', trueNames: '' };
}

export function entryDraft(entry: LoreEntry): EntryDraft {
  return {
    name: entry.name,
    kind: entry.kind,
    keywords: entry.keywords.join(', '),
    content: entry.content,
    trueNames: entry.true_names.join(', '),
  };
}

/** 보내기 전에 알릴 것. 칸 이름 → 글 */
export function entryHints(draft: EntryDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > ENTRY_NAME_MAX) hints.name = `이름은 ${ENTRY_NAME_MAX}자까지입니다.`;
  if (draft.content.length > ENTRY_CONTENT_MAX) hints.content = `설명은 ${ENTRY_CONTENT_MAX}자까지입니다.`;
  const keywords = wordsHint(splitWords(draft.keywords), KEYWORDS_MAX, KEYWORD_LENGTH, '키워드');
  if (keywords) hints.keywords = keywords;
  const names = draft.kind === 'person' ? wordsHint(splitWords(draft.trueNames), TRUE_NAMES_MAX, TRUE_NAME_LENGTH, '이름') : null;
  if (names) hints.true_names = names;
  return hints;
}

/** 더할 때와 고칠 때 같은 본문이다. 지목할 이름은 인물일 때만, 아니면 비운다 */
export function toEntryBody(draft: EntryDraft): LoreEntryCreate {
  return {
    name: draft.name.trim(),
    kind: draft.kind,
    keywords: splitWords(draft.keywords),
    content: draft.content,
    true_names: draft.kind === 'person' ? splitWords(draft.trueNames) : [],
  };
}
