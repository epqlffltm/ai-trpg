// web/apps/web/src/pages/trpg/studio/scenarios/Items.test.tsx
// 시나리오의 물건·돈 탭(B9). 화폐와 시작 소지품을 탭의 저장으로, 물건 규칙과 프리젠의 소지품을 창에서 바로 보내기.
// 붙인 로어북의 물건 항목을 늘어놓기와 로어북에 없는 물건의 규칙. 입력의 순수한 함수(규칙, 소지품의 착용, 화폐).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { ItemRule } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { currencyDraft, currencyHints, moneyText, toCurrency } from './currencyForm';
import { aidHints, aidLine, newAidDraft } from './itemAidsForm';
import { effectHints, newEffectDraft, toggleCure } from './itemEffectsForm';
import { itemRuleDraft, itemRuleHints, itemRuleLine, toItemRule } from './itemRuleForm';
import { stacksHints } from './stacksForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const SWORD = '00000000-0000-4000-8000-00000000a001';
const POTION = '00000000-0000-4000-8000-00000000a002';
const GONE = '00000000-0000-4000-8000-00000000a003';

const SWORD_RULE = {
  entry_id: SWORD,
  kind: 'gear',
  rarity: 'rare',
  effects: [],
  price: 30,
  slots: ['main_hand', 'off_hand'],
  slot_count: 2,
  attack: 2,
  ap: null,
  defense: null,
  guard: null,
  ward: null,
  aids: [],
  resistances: [],
};

const KNIGHT = { name: '기사', description: '', sheet: { abilities: { str: 16, dex: 10, con: 14 }, max_hp: 14 }, items: [], money: 0 };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function scenario(extra: Record<string, unknown> = {}) {
  return scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    openings: ['종이 울린다.'],
    pregens: [KNIGHT],
    character_modes: ['pregen'],
    items: [SWORD_RULE],
    ...extra,
  });
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenario(start);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [entry(SWORD, '양손검', 'item'), entry('p1', '문지기', 'person'), entry(POTION, '약초 꾸러미', 'item')]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  });
}

function patches(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as Record<string, unknown>);
}

async function itemsPanel() {
  return within(await screen.findByRole('tabpanel', { name: '물건·돈' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('물건·돈 탭', () => {
  it('화폐와 시작 소지품(착용)을 탭의 저장으로 보낸다. 착용 칸의 수가 맞지 않으면 막는다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=items`);

    const panel = await itemsPanel();
    const form = within(await panel.findByRole('form', { name: '물건·돈' }));
    await userEvent.click(form.getByRole('checkbox', { name: '이 시나리오는 돈을 쓴다' }));
    await userEvent.type(form.getByRole('textbox', { name: '이름' }), '금화');
    await userEvent.type(form.getByRole('textbox', { name: '단위(선택)' }), '닢');
    await userEvent.clear(form.getByRole('textbox', { name: '모두의 시작 돈' }));
    await userEvent.type(form.getByRole('textbox', { name: '모두의 시작 돈' }), '20');

    await userEvent.click(form.getByRole('button', { name: '시작 소지품 더하기' }));
    const row = within(form.getByRole('group', { name: '시작 소지품 1' }));
    expect(row.getByRole('combobox', { name: '물건' })).toHaveValue(SWORD);
    await userEvent.click(row.getByRole('checkbox', { name: '주손' }));
    expect(row.getByText('이 물건은 2칸을 차지합니다. 착용할 칸을 그만큼 골라 주세요.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(row.getByRole('checkbox', { name: '보조손' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)[0]).toEqual({
      currency: { name: '금화', unit: '닢', starting: 20, sell_percent: 50 },
      starting_items: [{ entry_id: SWORD, count: 1, wear: ['main_hand', 'off_hand'] }],
    });
  });

  it('물건 항목마다 규칙을 보이고, 창에서 바꾸면 목록을 통째로 보낸다. 로어북에 없는 물건의 규칙은 지울 수 있다', async () => {
    const { seen } = signedIn({ items: [SWORD_RULE, { ...SWORD_RULE, entry_id: GONE, price: null, attack: null, slots: [], slot_count: 1 }] });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=items`);

    const panel = await itemsPanel();
    const list = within(await panel.findByRole('list', { name: '물건 규칙' }));
    expect(list.getByText('장비 · 희귀 · 값 30 · 주손, 보조손 중 2칸 · 공격 +2')).toBeInTheDocument();
    expect(list.getByText('규칙 없음(장비 · 보통)')).toBeInTheDocument();
    expect(list.queryByText('문지기')).toBeNull();

    await userEvent.click(list.getByRole('button', { name: '약초 꾸러미 규칙 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '종류' }), 'consumable');
    await userEvent.click(dialog.getByRole('button', { name: '효과 더하기' }));
    expect(dialog.getByText('양을 고르세요.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(within(dialog.getByRole('group', { name: '효과 1' })).getByRole('combobox', { name: '양' }), 'light');
    await userEvent.click(dialog.getByRole('checkbox', { name: '던지는 판정을 따로 적는다' }));
    expect(dialog.getByText('던지는 판정의 능력치를 고르세요.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('checkbox', { name: '던지는 판정을 따로 적는다' }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const sent = patches(seen)[0]?.items as ItemRule[];
    expect(sent).toHaveLength(3);
    expect(sent[2]).toMatchObject({ entry_id: POTION, kind: 'consumable', effects: [{ kind: 'heal', magnitude: 'light' }], slots: [], attack: null });

    await userEvent.click(list.getByRole('button', { name: '(붙인 로어북에 없는 물건) 규칙 고치기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '규칙 지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1]?.items as ItemRule[]).map((rule) => rule.entry_id)).toEqual([SWORD, POTION]);
  });

  it('프리젠의 소지품과 돈을 창에서 바꾸고, 이름과 시트는 그대로 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=items`);

    const panel = await itemsPanel();
    await userEvent.click(await panel.findByRole('button', { name: '기사의 소지품 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '소지품 더하기' }));
    await userEvent.selectOptions(within(dialog.getByRole('group', { name: '소지품 1' })).getByRole('combobox', { name: '물건' }), POTION);
    await userEvent.clear(dialog.getByRole('textbox', { name: '더 받는 돈' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '더 받는 돈' }), '15');
    expect(dialog.getByText('화폐가 없으면 게시 점검이 알립니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]).toEqual({ pregens: [{ ...KNIGHT, items: [{ entry_id: POTION, count: 1, wear: [] }], money: 15 }] });
    expect(await panel.findByText('약초 꾸러미 1 · 돈 15')).toBeInTheDocument();
  });
});

describe('물건·돈 입력', () => {
  it('규칙: 관통력은 공격 보정과 함께, 칸의 수는 고른 칸까지. 종류에 맞지 않는 칸은 비운다', () => {
    const draft = itemRuleDraft(SWORD_RULE as ItemRule);
    expect(itemRuleHints({ ...draft, combat: { ...draft.combat, attack: '', ap: '2' } }).ap).toBe('관통력은 공격 보정이 있는 무기에만 적습니다.');
    expect(itemRuleHints({ ...draft, slotCount: '3' }).slot_count).toBeDefined();
    expect(itemRuleHints({ ...draft, price: '0' }).price).toBeDefined();
    expect(toItemRule(SWORD, { ...draft, kind: 'consumable' })).toMatchObject({ slots: [], slot_count: 1, attack: null, effects: [] });
    expect(toItemRule(SWORD, { ...draft, slots: [] })).toMatchObject({ attack: null, slot_count: 1 });
  });

  it('규칙: 효과는 읽은 그대로 소모품에만 돌려 보낸다', () => {
    const effects = [{ kind: 'cure', injuries: ['poisoned'] }, { kind: 'injure', injury: 'stunned' }];
    const antidote = itemRuleDraft({ ...SWORD_RULE, entry_id: POTION, kind: 'consumable', slots: [], attack: null, effects } as ItemRule);
    expect(toItemRule(POTION, antidote).effects).toEqual(effects);
    expect(toItemRule(POTION, { ...antidote, kind: 'gear' }).effects).toEqual([]);
    expect(toItemRule(SWORD, itemRuleDraft(undefined)).effects).toEqual([]);
  });

  it('효과: 회복과 피해는 함께 못 하고, 같은 종류는 한 번씩, 같은 부상을 두 번 입히지 않는다', () => {
    const heal = { ...newEffectDraft('heal'), magnitude: 'light' };
    const damage = { ...newEffectDraft('damage'), magnitude: 'light' };
    const stun = { ...newEffectDraft('injure'), injury: 'stunned' };
    expect(effectHints([heal, damage]).effects).toBe('회복과 피해는 한 물건에 함께 적지 않습니다.');
    expect(effectHints([heal, heal]).effects).toBe('회복, 풀기, 피해는 한 번씩만 적습니다.');
    expect(effectHints([stun, stun]).effects).toBe('같은 부상을 두 번 입힙니다.');
    expect(effectHints([newEffectDraft('cure')])['effect.0']).toBe('풀 부상을 하나 이상 고르세요.');
    expect(effectHints([damage, stun])).toEqual({});
    expect(toggleCure(['stunned'], 'poisoned', null)).toEqual(['stunned', 'poisoned']);
  });

  it('효과: 목록의 줄', () => {
    const rule = { ...SWORD_RULE, kind: 'consumable', slots: [], attack: null, price: null, effects: [{ kind: 'damage', magnitude: 'light' }, { kind: 'injure', injury: 'poisoned' }], throw: { ability: 'dex', difficulty: null }, aids: [{ act: 'treat', bonus: 2, wear: 'always' }] } as unknown as ItemRule;
    expect(itemRuleLine(rule, null)).toBe('소모품 · 희귀 · 피해 light · 부상: poisoned · 던짐 · 치료 +2(쓰면 늘 없어짐)');
  });

  it('규칙: 던지는 판정은 장비에도 보낸다. 끄면 보내지 않는다', () => {
    const thrown = { ability: 'dex', difficulty: null };
    const firebomb = itemRuleDraft({ ...SWORD_RULE, entry_id: POTION, kind: 'consumable', slots: [], attack: null, throw: thrown } as ItemRule);
    expect(toItemRule(POTION, firebomb).throw).toEqual(thrown);
    expect(toItemRule(POTION, { ...firebomb, kind: 'gear' }).throw).toEqual(thrown);
    expect(toItemRule(POTION, { ...firebomb, throw: { ...firebomb.throw, on: false } }).throw).toBeNull();
    expect(toItemRule(SWORD, itemRuleDraft(undefined)).throw).toBeNull();
  });

  it('규칙: 거드는 행동은 모든 물건에 읽은 그대로 보내고, 비운 보정은 0 이다(#802)', () => {
    const aids = [{ act: 'pick', bonus: 2, wear: 'on_fail' }, { act: 'cross', bonus: 0, wear: 'never' }] as ItemRule['aids'];
    const lockpick = itemRuleDraft({ ...SWORD_RULE, aids } as ItemRule);
    expect(lockpick.aids).toEqual([{ act: 'pick', bonus: '2', wear: 'on_fail' }, { act: 'cross', bonus: '', wear: 'never' }]);
    expect(toItemRule(SWORD, lockpick).aids).toEqual(aids);
    expect(toItemRule(SWORD, { ...lockpick, kind: 'consumable' }).aids).toEqual(aids);
    expect(toItemRule(SWORD, itemRuleDraft(undefined)).aids).toEqual([]);
  });

  it('거들기: 보정은 0~10, 같은 행동은 한 번. 새 줄은 아직 적지 않은 행동이다', () => {
    const pick = { act: 'pick', bonus: '2', wear: 'on_fail' } as const;
    expect(aidHints([pick])).toEqual({});
    expect(aidHints([{ ...pick, bonus: '11' }])['aid.0']).toBe('보정은 0~10 사이의 정수입니다.');
    expect(aidHints([pick, { ...pick, bonus: '1' }]).aids).toBe('한 물건에 같은 행동의 거들기를 두 번 적었습니다.');
    expect(newAidDraft([])).toEqual({ act: 'treat', bonus: '', wear: 'always' });
    expect(newAidDraft([{ act: 'treat', bonus: '', wear: 'always' }])).toEqual({ act: 'pick', bonus: '', wear: 'never' });
    expect(aidLine({ act: 'cross', bonus: 0, wear: 'never' })).toBe('넘기(없어지지 않음)');
  });

  it('소지품: 같은 물건, 개수, 착용 칸의 수, 겹치는 칸을 알린다', () => {
    const rules = [SWORD_RULE as ItemRule, { ...SWORD_RULE, entry_id: POTION, slots: ['main_hand'], slot_count: 1 } as ItemRule];
    expect(stacksHints([{ entryId: SWORD, count: '1', wear: [] }, { entryId: SWORD, count: '2', wear: [] }], rules)[1]).toContain('같은 물건');
    expect(stacksHints([{ entryId: SWORD, count: '100', wear: [] }], rules)[0]).toContain('개수');
    expect(
      stacksHints(
        [
          { entryId: SWORD, count: '1', wear: ['main_hand', 'off_hand'] },
          { entryId: POTION, count: '1', wear: ['main_hand'] },
        ],
        rules,
      ),
    ).toEqual({ 1: '다른 줄이 착용한 칸과 겹칩니다.' });
  });

  it('화폐: 끄면 null, 이름은 꼭, 백분율은 0~100. 돈의 글', () => {
    expect(toCurrency({ ...currencyDraft(null), enabled: false })).toBeNull();
    expect(Object.keys(currencyHints({ ...currencyDraft(null), enabled: true, sellPercent: '101' })).sort()).toEqual(['currency_name', 'sell_percent']);
    expect(moneyText({ name: '금화', unit: '닢', starting: 0, sell_percent: 50 }, 30)).toBe('금화 30닢');
    expect(moneyText(null, 30)).toBe('돈 30');
  });
});
