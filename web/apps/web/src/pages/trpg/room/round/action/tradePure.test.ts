// web/apps/web/src/pages/trpg/room/round/action/tradePure.test.ts
// 돈과 사고팔기(#278)의 순수한 함수. 돈의 글, 사고파는 값의 어림, 고를 수 있는 상인과 물건, 보내기 전의 검사,
// 라운드에 보일 행동과 결과의 글을 본다.

import { describe, expect, it } from 'vitest';
import type { Declaration, SceneCast, TableDetail, TableMember } from '../../../../../api/types';
import { ME, member, OTHER, RULES, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { amountLabel, buyingCost, moneyLabel, sellingGain } from '../../money';
import { actionLabel, outcomeLine } from '../roundView';
import { actionHint, emptyActionDraft, type ActionDraft } from './actionDraft';
import { availableKinds, merchants, sellableItems, stockChoices, type ActionContext } from './actionOptions';

const SHOP = '00000000-0000-4000-8000-0000000000f4';
const ANGRY = '00000000-0000-4000-8000-0000000000f5';
const COIN = { name: '금화', unit: '닢', sell_percent: 50 };
const rules = RULES as unknown as TableDetail['rules'];

function cast(shopAttitude = 'neutral'): SceneCast {
  const torch = { entry_id: 'i4', name: '횃불', rarity: 'normal', count: 3, equipped: false, price: 5 };
  return {
    round: 2,
    people: [
      { id: SHOP, name: '상인', named: false, status: 'alive', injuries: [], attitude: shopAttitude, merchant: true, items: [torch, { ...torch, entry_id: 'i9', name: '검', equipped: true, price: 50 }] },
      { id: ANGRY, name: '성난 상인', named: false, status: 'alive', injuries: [], attitude: 'hostile', merchant: true, items: [torch] },
    ],
    monsters: [],
  } as unknown as SceneCast;
}

function context(money: number, extra: Record<string, unknown> = {}, scene: SceneCast | null = cast()): ActionContext {
  const table = tableDetail('t', {
    status: 'playing',
    currency: COIN,
    members: [
      member(ME, { character: { name: '렌', description: '' }, sheet: sheet({ money, items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', count: 2 }] }) }),
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
    ],
    items: [
      { entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light', price: 9 },
      { entry_id: 'i4', name: '횃불', kind: 'gear', rarity: 'normal', heals: null, price: 5 },
    ],
    ...extra,
  }) as unknown as TableDetail;
  return { table, me: table.members[0] as TableMember, cast: scene };
}

function draft(changes: Partial<ActionDraft>): ActionDraft {
  return { ...emptyActionDraft(rules), ...changes };
}

describe('money', () => {
  it('돈은 화폐의 이름과 단위로, 화폐가 없으면 숫자만', () => {
    expect(moneyLabel(COIN, 1200)).toBe('금화 1,200닢');
    expect(amountLabel(null, 7)).toBe('7');
  });

  it('사는 값은 값 × 개수, 파는 값은 하나씩 내림한 뒤 × 개수(서버와 같다)', () => {
    expect(buyingCost(5, 3)).toBe(15);
    expect(sellingGain(COIN, 9, 3)).toBe(12);
  });
});

describe('사고팔기와 돈 건네기의 고를 거리', () => {
  it('화폐가 있고 거래하는 상인이 있으면 사기·팔기, 돈이 있으면 돈 건네기', () => {
    expect(availableKinds(context(30))).toEqual(expect.arrayContaining(['buy', 'sell', 'pay']));
    expect(availableKinds(context(0))).not.toContain('pay');
    expect(availableKinds(context(30, { currency: null }))).not.toEqual(expect.arrayContaining(['buy']));
    expect(availableKinds(context(30, { currency: { ...COIN, sell_percent: 0 } }))).not.toContain('sell');
    expect(availableKinds(context(30, {}, null))).not.toContain('buy');
  });

  it('상인은 살아 있고 적대하지 않는 이. 파는 것은 장비가 아니고 값이 있는 것', () => {
    const ctx = context(30);
    expect(merchants(ctx)).toEqual([{ value: `npc:${SHOP}`, label: '상인' }]);
    expect(merchants(context(30, {}, cast('hostile')))).toEqual([]);
    expect(stockChoices(ctx, `npc:${SHOP}`)).toEqual([{ value: 'i4', label: '횃불 ×3 · 5닢' }]);
    expect(sellableItems(ctx).map((item) => item.entry_id)).toEqual(['i1']);
  });

  it('보내기 전에 재고, 돈, 가진 개수를 본다', () => {
    const buy = draft({ kind: 'buy', target: `npc:${SHOP}`, item: 'i4' });
    expect(actionHint({ ...buy, count: 3 }, context(30))).toBeNull();
    expect(actionHint({ ...buy, count: 4 }, context(30))).toBe('개수는 3개까지입니다.');
    expect(actionHint({ ...buy, count: 3 }, context(10))).toBe('돈이 모자랍니다(값 15닢, 가진 돈 10닢).');
    expect(actionHint(draft({ kind: 'sell', target: `npc:${SHOP}`, item: 'i1', count: 3 }), context(0))).toBe('개수는 2개까지입니다.');
    expect(actionHint(draft({ kind: 'pay', target: `member:${OTHER}`, amount: 31 }), context(30))).toBe('가진 돈(30닢)보다 많이 건넬 수 없습니다.');
    expect(actionHint(draft({ kind: 'pay', target: `member:${OTHER}`, amount: 30 }), context(30))).toBeNull();
  });
});

describe('라운드의 글', () => {
  const table = context(30).table;

  it('행동은 물건과 개수, 돈과 받는 사람', () => {
    expect(actionLabel({ kind: 'buy', npc: SHOP, item: 'i4', count: 2 }, table)).toBe('사기 · 횃불 ×2');
    expect(actionLabel({ kind: 'pay', target: OTHER, amount: 12 }, table)).toBe('돈 건네기 · 12닢 → 미아');
  });

  it('결과는 오간 돈과 남은 돈, 못 했으면 까닭', () => {
    const trade = { side: 'buy', name: '횃불', count: 2, price: 10, traded: true, reason: null, total: 2, money: 20 };
    const line = (outcome: unknown) => outcomeLine(outcome as Declaration['outcome'], rules, COIN);
    expect(line({ trade })).toBe('횃불 ×2 샀습니다(낸 돈 10닢, 남은 돈 20닢)');
    expect(line({ trade: { ...trade, side: 'sell', price: 4, money: 34 } })).toBe('횃불 ×2 팔았습니다(받은 돈 4닢, 가진 돈 34닢)');
    expect(line({ trade: { ...trade, traded: false, reason: 'out_of_stock' } })).toBe('사지 못했습니다: 상인의 재고가 모자랐습니다.');
    expect(line({ pay: { amount: 5, paid: true, reason: null, target: { user_id: OTHER, character_name: '미아' }, remaining: 25 } })).toBe(
      '5닢 → 미아(남은 돈 25닢)',
    );
    expect(line({ pay: { amount: 5, paid: false, reason: 'target_gone', target: { user_id: OTHER, character_name: null }, remaining: 30 } })).toBe(
      '건네지 못했습니다: 받을 사람이 없었습니다.',
    );
  });
});
