// web/apps/web/src/pages/trpg/room/round/actionOutcome.test.ts
// 물건, 훔치기와 빼앗기, 쉬기와 기다리기의 결과 한 줄. 못 한 것과 덜 한 것의 까닭, 모르는 까닭은 이름 그대로.

import { describe, expect, it } from 'vitest';
import type { Declaration, Ruleset } from '../../../../api/types';
import { RULES } from '../../../../test/tableFixtures';
import { giveLine, itemUseLine, lootLine, putDownLine, restLine, stealLine, takeLine, waitLine } from './actionOutcome';
import { outcomeLine } from './roundView';

const rules = RULES as unknown as Ruleset;
const asOutcome = (value: unknown) => value as Declaration['outcome'];

describe('행동의 결과의 까닭', () => {
  it('물건: 쓰기, 건네기, 줍기(덜 주움), 내려놓기', () => {
    expect(itemUseLine({ used: false, name: '약초', remaining: 0, reason: 'not_held' } as never)).toBe('쓰지 못했습니다(그만큼 가지고 있지 않았습니다)');
    expect(giveLine({ given: false, reason: 'too_many' } as never)).toBe('건네지 못했습니다(받는 쪽이 더 가질 수 없었습니다)');
    expect(takeLine({ name: '약초', count: 3, taken: 1, reason: 'not_enough' } as never)).toBe('약초 ×1 주웠습니다(남은 것이 모자라 남은 만큼만)');
    expect(takeLine({ name: '약초', count: 3, taken: 0, reason: 'gone' } as never)).toBe('줍지 못했습니다(앞사람이 가져가 남은 것이 없었습니다)');
    expect(takeLine({ name: '약초', count: 1, taken: 1, reason: null } as never)).toBe('약초 ×1 주웠습니다');
    expect(putDownLine({ put: false, name: '약초', count: 1, reason: 'not_held' } as never)).toBe('내려놓지 못했습니다(내려놓을 만큼 가지고 있지 않았습니다)');
  });

  it('훔치기와 빼앗기: 들킴은 까닭 없이, 싸움, 이미 없음, 깨어 있음, 그만큼만', () => {
    expect(stealLine({ stolen: false, fight: false, reason: null } as never)).toBe('훔치지 못했습니다');
    expect(stealLine({ stolen: false, fight: true, reason: null } as never)).toBe('훔치지 못했고 싸움이 붙었습니다');
    expect(stealLine({ stolen: false, fight: false, reason: 'gone' } as never)).toBe('훔치지 못했습니다(대상이 그 물건을 더는 지니지 않았습니다)');
    expect(lootLine({ looted: false, reason: 'awake' } as never)).toBe('가져오지 못했습니다(대상이 깨어 있었습니다)');
    expect(lootLine({ looted: true, name: '은화', count: 99, reason: 'full' } as never)).toBe('은화 ×99 가져왔습니다(더 가질 수 없어 그만큼만)');
  });

  it('쉬기와 기다리기: 다침, 쓰러짐, 무작위 조우의 기습, 모두가 기다리지 않음. 모르는 까닭은 이름 그대로', () => {
    expect(restLine({ rested: false, reason: 'ambushed', before: 5, after: 5 } as never)).toBe('쉬지 못했습니다(쉬는 중에 몬스터가 덮쳤습니다)');
    expect(restLine({ rested: true, reason: null, before: 5, after: 9 } as never)).toBe('HP 5 → 9');
    expect(waitLine({ waited: false, minutes: 60, reason: 'not_all' } as never)).toBe('기다리지 못했습니다(모두가 기다리지는 않았습니다)');
    expect(outcomeLine(asOutcome({ rest: { rested: false, reason: 'cursed', before: 1, after: 1 } }), rules)).toBe('쉬지 못했습니다(cursed)');
  });
});
