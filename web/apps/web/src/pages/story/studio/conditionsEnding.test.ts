// web/apps/web/src/pages/story/studio/conditionsEnding.test.ts
// 조건의 "그 엔딩을 본 적이 있다(회차, ending_seen)"를 본다. 대상은 세계관의 엔딩에서 고르고, 없는 엔딩이면 다시 고르라고 알린다.
import { describe, expect, it } from 'vitest';

import { conditionsHints, savedChoices, targetChoices, toConditions } from './conditionsForm';

const world = {
  places: [],
  items: [],
  slots: [],
  cast: [],
  endings: [{ id: 'solo', name: '혼자인 여름' }],
};

describe('회차 조건', () => {
  it('대상은 세계관의 엔딩에서 고른다', () => {
    const choices = savedChoices(world, [], []);

    expect(targetChoices('ending_seen', choices)).toEqual([{ id: 'solo', name: '혼자인 여름' }]);
    expect(targetChoices('ending_seen', { ...choices, endings: undefined })).toEqual([]);
  });

  it('없는 엔딩은 다시 고르라고 알리고, 보낼 때는 대상만 싣는다', () => {
    const choices = savedChoices(world, [], []);
    const draft = { match: 'all' as const, items: [{ kind: 'ending_seen' as const, target: 'ghost', value: '', count: '1' }] };

    expect(conditionsHints(draft, choices)).toEqual({ 0: '없는 대상입니다. 다시 골라 주세요.' });
    expect(toConditions({ ...draft, items: [{ ...draft.items[0]!, target: 'solo' }] }).items).toEqual([{ kind: 'ending_seen', target: 'solo', count: 1 }]);
  });
});
