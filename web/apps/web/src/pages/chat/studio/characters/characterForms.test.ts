// web/apps/web/src/pages/chat/studio/characters/characterForms.test.ts
// 캐릭터 만들기(C6)의 입력과 글의 순수한 함수: 기본(태그 나누기, 상한), 소개의 크기, 말, 시작 상황, 탭, 문제의 글, 걸러진 것.

import { describe, expect, it } from 'vitest';
import type { AssetCharacterDetail } from '../../../../api/types';
import { basicsDraft, basicsHints, parseTags, toBasicsBody, type BasicsDraft } from './basicsForm';
import { isTab, tabOf } from './characterTabs';
import { problemLine } from './publishProblems';
import { removedLine } from './removedHtml';
import {
  addStart,
  hourOf,
  moveStartUp,
  removeStart,
  startDrafts,
  STARTS_MAX,
  startsHints,
  toStartsBody,
  type StartDraft,
} from './startsForm';
import { INTRO_MAX_BYTES, introHint, speechHints, utf8Bytes } from './textsForm';

const BASICS: BasicsDraft = { name: '세라', age: '', gender: '', tags: '', rating: 'all', visibility: 'private' };

describe('기본', () => {
  it('태그는 쉼표로 나누고 빈 것과 겹친 것을 뺀다', () => {
    expect(parseTags(' 판타지, ,기사,판타지 ')).toEqual(['판타지', '기사']);
    expect(parseTags('')).toEqual([]);
  });

  it('이름은 빈칸을 빼고 1~50자, 태그는 10개에 하나 20자', () => {
    expect(basicsHints({ ...BASICS, name: '   ' }).name).toMatch(/적어 주세요/);
    expect(basicsHints({ ...BASICS, name: '가'.repeat(51) }).name).toMatch(/50자/);
    expect(basicsHints({ ...BASICS, tags: Array.from({ length: 11 }, (_, i) => `t${i}`).join(',') }).tags).toMatch(/10개/);
    expect(basicsHints({ ...BASICS, tags: '가'.repeat(21) }).tags).toMatch(/20자/);
    expect(basicsHints({ ...BASICS, age: '가'.repeat(21), gender: '가'.repeat(21) })).toMatchObject({ age: expect.any(String), gender: expect.any(String) });
    expect(basicsHints(BASICS)).toEqual({});
  });

  it('보낼 때 다듬는다', () => {
    expect(toBasicsBody({ ...BASICS, name: ' 세라 ', age: ' 스물 ', tags: '기사, 기사' })).toEqual({
      name: '세라',
      age: '스물',
      gender: '',
      tags: ['기사'],
      rating: 'all',
      visibility: 'private',
    });
    const character = { name: '렌', age: '20', gender: '남', tags: ['a', 'b'], rating: 'adult', visibility: 'public' } as AssetCharacterDetail;
    expect(basicsDraft(character).tags).toBe('a, b');
  });
});

describe('글', () => {
  it('소개는 UTF-8 로 50KB 까지다', () => {
    expect(utf8Bytes('가')).toBe(3);
    expect(introHint('a'.repeat(INTRO_MAX_BYTES))).toBeUndefined();
    expect(introHint('가'.repeat(INTRO_MAX_BYTES / 3 + 1))).toMatch(/50KB/);
  });

  it('인사말과 말투 예시는 2,000자씩', () => {
    expect(speechHints({ greeting: '가'.repeat(2001), speechExamples: '' })).toHaveProperty('greeting');
    expect(speechHints({ greeting: '', speechExamples: '가'.repeat(2001) })).toHaveProperty('speech_examples');
    expect(speechHints({ greeting: '가'.repeat(2000), speechExamples: '' })).toEqual({});
  });
});

describe('시작 상황', () => {
  const one: StartDraft = { title: '비 오는 밤', situation: '문을 두드린다.', hour: '21' };

  it('시각은 0~23 의 정수다', () => {
    expect([hourOf('0'), hourOf(' 23 '), hourOf('24'), hourOf('1.5'), hourOf(''), hourOf('-1')]).toEqual([0, 23, null, null, null, null]);
  });

  it('칸마다 알린다', () => {
    expect(startsHints([one])).toEqual({});
    expect(startsHints([{ title: ' ', situation: ' ', hour: 'x' }])[0]).toEqual({
      title: expect.stringMatching(/제목/),
      situation: expect.stringMatching(/상황/),
      hour: expect.stringMatching(/0~23/),
    });
    expect(startsHints([{ ...one, title: '가'.repeat(31), situation: '가'.repeat(2001) }])[0]).toMatchObject({
      title: expect.stringMatching(/30자/),
      situation: expect.stringMatching(/2000자/),
    });
  });

  it('더하기는 다섯까지, 지우기와 앞으로', () => {
    const full = Array.from({ length: STARTS_MAX }, () => one);
    expect(addStart(full)).toBe(full);
    expect(addStart([])).toEqual([{ title: '', situation: '', hour: '12' }]);
    const two = [one, { ...one, title: '둘' }];
    expect(moveStartUp(two, 1).map((start) => start.title)).toEqual(['둘', '비 오는 밤']);
    expect(moveStartUp(two, 0)).toBe(two);
    expect(removeStart(two, 0).map((start) => start.title)).toEqual(['둘']);
  });

  it('보낼 때 제목만 다듬고 시각을 수로 바꾼다', () => {
    expect(toStartsBody([{ ...one, title: ' 밤 ', situation: '\n글\n' }])).toEqual({ starts: [{ title: '밤', situation: '\n글\n', hour: 21 }] });
    expect(startDrafts([{ title: 'a', situation: 'b', hour: 7 }])).toEqual([{ title: 'a', situation: 'b', hour: '7' }]);
  });
});

describe('탭과 점검의 글', () => {
  it('주소의 탭', () => {
    expect([tabOf('map'), tabOf('affection'), tabOf(null)]).toEqual(['map', 'basics', 'basics']);
    expect([isTab('intro'), isTab('affection')]).toEqual([true, false]);
  });

  it('문제는 그 묶음을 가리킨다. 모르는 이름은 그대로', () => {
    expect(problemLine('start_missing')).toEqual({ text: '시작 상황이 하나도 없습니다.', section: 'starts' });
    expect(problemLine('item_missing').section).toBe('items');
    expect(problemLine('new_problem')).toEqual({ text: 'new_problem', section: null });
  });

  it('걸러진 것', () => {
    expect(removedLine({ kind: 'tag', name: 'script' })).toBe('허용하지 않는 태그: script');
  });
});
