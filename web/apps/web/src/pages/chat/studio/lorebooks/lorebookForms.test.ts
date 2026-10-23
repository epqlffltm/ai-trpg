// web/apps/web/src/pages/chat/studio/lorebooks/lorebookForms.test.ts
// chat 의 로어북과 캐릭터의 로어북 탭의 입력: 이름과 설명, 항목(꼭 있는 칸, 키워드의 개수·길이·겹침, 보낼 때 다듬기),
// 붙이기(3 개, 겹치지 않기), 앞으로, 떼기, 고르기 목록에서 찾기.

import { describe, expect, it } from 'vitest';
import type { AssetLorebookDetail, AssetLorebookSummary } from '../../../../api/types';
import {
  attachedLorebooks,
  attachLorebook,
  detachLorebook,
  lorebookChoices,
  LOREBOOKS_MAX,
  moveLorebookUp,
  toLorebooksBody,
} from '../characters/lorebooksForm';
import { addEntry, changeEntry, ENTRIES_MAX, entriesHints, entryDrafts, removeEntry, splitKeywords, toEntriesBody, type EntryDraft } from './entriesForm';
import { infoHints, nameHint, toInfoBody } from './lorebookForm';

describe('이름과 설명', () => {
  it('이름은 빈칸을 빼고 1~50자, 설명은 1000자', () => {
    expect([nameHint(' '), nameHint('가'.repeat(51)), nameHint(' 바다 ')]).toEqual([expect.stringMatching(/적어/), expect.stringMatching(/50자/), undefined]);
    expect(infoHints({ name: '바다', description: '가'.repeat(1001) })).toEqual({ description: expect.stringMatching(/1000자/) });
    expect(toInfoBody({ name: ' 바다 ', description: ' 메모 ' })).toEqual({ name: '바다', description: ' 메모 ' });
  });
});

describe('항목', () => {
  const tide: EntryDraft = { id: 'lore-1', name: '밀물', kind: 'event', keywords: '바다, 물때', content: '하루 두 번 든다.', constant: false };

  it('이름과 내용은 꼭 있어야 하고 길이를 넘지 않는다', () => {
    expect(entriesHints([tide])).toEqual({});
    expect(entriesHints([{ ...tide, name: ' ', content: ' ' }])['lore-1']).toEqual({ name: expect.any(String), content: expect.any(String) });
    expect(entriesHints([{ ...tide, name: '가'.repeat(101), content: '가'.repeat(501) }])['lore-1']).toEqual({
      name: expect.stringMatching(/100자/),
      content: expect.stringMatching(/500자/),
    });
  });

  it('키워드는 5 개, 하나에 30자, 대소문자만 다른 것도 겹친 것이다', () => {
    expect(splitKeywords(' a, ,b ,')).toEqual(['a', 'b']);
    expect(entriesHints([{ ...tide, keywords: 'a,b,c,d,e,f' }])['lore-1']?.keywords).toMatch(/5개/);
    expect(entriesHints([{ ...tide, keywords: '가'.repeat(31) }])['lore-1']?.keywords).toMatch(/30자/);
    expect(entriesHints([{ ...tide, keywords: 'Sea, sea' }])['lore-1']?.keywords).toMatch(/두 번/);
  });

  it('더하기는 200 개까지, 바꾸기와 지우기, 보낼 때 다듬는다', () => {
    const full = Array.from({ length: ENTRIES_MAX }, (_, i) => ({ ...tide, id: `lore-${i}` }));
    expect(addEntry(full, 'x')).toBe(full);
    expect(addEntry([], 'lore-9')).toEqual([{ id: 'lore-9', name: '', kind: 'other', keywords: '', content: '', constant: false }]);
    const two = changeEntry([tide, { ...tide, id: 'lore-2' }], 'lore-2', { constant: true });
    expect(removeEntry(two, 'lore-1').map((entry) => entry.constant)).toEqual([true]);
    expect(toEntriesBody([{ ...tide, name: ' 밀물 ', content: ' 든다. ', keywords: '바다 , 물때' }])).toEqual({
      entries: [{ id: 'lore-1', name: '밀물', kind: 'event', keywords: ['바다', '물때'], content: '든다.', constant: false }],
    });
    const lorebook = { entries: [{ id: 'lore-1', name: '밀물', kind: 'event', keywords: ['바다', '물때'], content: '하루 두 번 든다.', constant: false }] };
    expect(entryDrafts(lorebook as unknown as AssetLorebookDetail)).toEqual([tide]);
  });
});

describe('캐릭터에 붙이기', () => {
  const summary = (id: string): AssetLorebookSummary => ({ id, name: id, entry_count: 0, latest_version: 1, updated_at: '' });

  it('3 개까지, 겹치지 않게, 빈 고름은 무시한다', () => {
    expect(attachLorebook(['a'], 'a')).toEqual(['a']);
    expect(attachLorebook(['a'], '')).toEqual(['a']);
    const full = Array.from({ length: LOREBOOKS_MAX }, (_, i) => `l${i}`);
    expect(attachLorebook(full, 'x')).toBe(full);
    expect(attachLorebook(['a'], 'b')).toEqual(['a', 'b']);
  });

  it('앞으로와 떼기', () => {
    expect(moveLorebookUp(['a', 'b', 'c'], 2)).toEqual(['a', 'c', 'b']);
    const ids = ['a', 'b'];
    expect(moveLorebookUp(ids, 0)).toBe(ids);
    expect(detachLorebook(ids, 'a')).toEqual(['b']);
    expect(toLorebooksBody(['b'])).toEqual({ lorebooks: ['b'] });
  });

  it('붙인 것은 고르기 목록에서 찾고, 없으면 비운다. 붙인 것은 고르는 칸에서 뺀다', () => {
    const mine = [summary('a'), summary('b')];
    expect(attachedLorebooks(['b', 'z'], mine)).toEqual([
      { id: 'b', summary: mine[1] },
      { id: 'z', summary: null },
    ]);
    expect(lorebookChoices(['b'], mine).map((lorebook) => lorebook.id)).toEqual(['a']);
  });
});
