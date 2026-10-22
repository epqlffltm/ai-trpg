// web/apps/web/src/pages/trpg/room/round/roundPure.test.ts
// 라운드(B6 의 ③)의 순수한 함수. 미리 보기 잇기, 결과의 글, 선언의 입력과 검사, 실패의 글을 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../../api/errors';
import type { Declaration, Round, Ruleset } from '../../../../api/types';
import { declaration, ME, OTHER, round, RULES } from '../../../../test/tableFixtures';
import { routeMessage } from '../streamPolicy';
import { declarationHints, hasOtherAction, initialDeclarationDraft, toDeclarationUpdate } from './declarationForm';
import { applyPreview, type NarrationPreview } from './preview';
import { describeCloseProblem, describeDeclarationProblem } from './roundProblem';
import { actionLabel, deathSaveLine, myDeclaration, outcomeLine, pastRounds, remainingSeconds } from './roundView';

const rules = RULES as unknown as Ruleset;

function chunk(seq: number, text: string, attempt = 1, roundNumber = 3) {
  return { round: roundNumber, attempt, seq, text };
}

function asRound(extra: Record<string, unknown>): Round {
  return round(3, extra) as unknown as Round;
}

function asDeclaration(userId: string, extra: Record<string, unknown>): Declaration {
  return declaration(userId, extra) as unknown as Declaration;
}

describe('applyPreview', () => {
  it('같은 시도의 조각을 차례로 잇고, 겹친 것은 버린다', () => {
    let preview: NarrationPreview | null = null;
    preview = applyPreview(preview, chunk(0, '엔진 소리가 '));
    preview = applyPreview(preview, chunk(1, '골목을 메운다.'));
    preview = applyPreview(preview, chunk(1, '골목을 메운다.'));
    expect(preview).toMatchObject({ text: '엔진 소리가 골목을 메운다.', nextSeq: 2, stalled: false });
  });

  it('조각을 놓치면 더 잇지 않는다. 도중에 붙으면 처음부터 잇지 않는다', () => {
    const missed = applyPreview(applyPreview(null, chunk(0, '가')), chunk(2, '다'));
    expect(missed).toMatchObject({ text: '가', stalled: true });
    expect(applyPreview(missed, chunk(3, '라'))).toBe(missed);
    expect(applyPreview(null, chunk(4, '중간'))).toMatchObject({ text: '', stalled: true });
  });

  it('시도가 커지면 새로 받고, 작은 시도와 지난 라운드는 버린다', () => {
    const first = applyPreview(null, chunk(0, '처음 글', 1));
    const second = applyPreview(first, chunk(0, '다시 쓴 글', 2));
    expect(second).toMatchObject({ attempt: 2, text: '다시 쓴 글' });
    expect(applyPreview(second, chunk(1, '늦은 조각', 1))).toBe(second);
    expect(applyPreview(second, chunk(0, '지난 라운드', 9, 2))).toBe(second);
    expect(applyPreview(second, chunk(0, '다음 라운드', 1, 4))).toMatchObject({ round: 4, text: '다음 라운드' });
  });

  it('스트림의 narration_preview 를 조각으로 읽는다. 모양이 틀리면 버린다', () => {
    expect(routeMessage({ event: 'narration_preview', data: JSON.stringify(chunk(0, '글')) })).toEqual({
      kind: 'preview',
      chunk: chunk(0, '글'),
    });
    expect(routeMessage({ event: 'narration_preview', data: '{"round":"3"}' })).toEqual({ kind: 'ignore' });
  });
});

describe('roundView', () => {
  it('판정의 결과는 눈, 보정, 합, 목표, 성공을 적는다', () => {
    const outcome = { roll: 13, modifier: 2, total: 15, target: 15, success: true, hindrance: null };
    expect(outcomeLine(outcome as unknown as Declaration['outcome'])).toBe('눈 13, 보정 +2, 합 15 / 목표 15 · 성공');
    const hindered = { ...outcome, modifier: -1, total: 12, success: false, hindrance: { disadvantage: true, injuries: [], penalty: 1, rolls: [13, 4] } };
    expect(outcomeLine(hindered as unknown as Declaration['outcome'])).toBe('눈 13, 보정 -1, 합 12 / 목표 15 · 불리함 · 실패');
    expect(outcomeLine({ turn_lost: 'downed' } as unknown as Declaration['outcome'])).toBe('행동하지 못했습니다.');
    expect(outcomeLine(null)).toBeNull();
  });

  it('판정은 능력과 난이도의 이름을, 다른 행동은 이름만 적는다. 난이도를 비우면 규칙의 기본이다', () => {
    expect(actionLabel({ kind: 'check', ability: 'dex', lethal: false }, rules)).toBe('판정 · 민첩, 보통');
    expect(actionLabel({ kind: 'search' }, rules)).toBe('찾기');
  });

  it('죽음의 굴림을 한 줄로', () => {
    const save = { user_id: ME, character_name: '렌', roll: 12, target: 10, success: true, successes: 2, failures: 1, fate: 'dying' } as const;
    expect(deathSaveLine(save)).toBe('렌: 죽음의 굴림 12 / 10 성공 (성공 2, 실패 1) · 아직 위태롭다');
  });

  it('지나간 라운드는 지금 라운드를 뺀다. 내 선언은 글이 있는 내 것이다', () => {
    const rounds = [1, 2, 3].map((number) => round(number) as unknown as Round);
    expect(pastRounds(rounds, rounds[2]).map((entry) => entry.number)).toEqual([1, 2]);
    const current = asRound({ declarations: [declaration(OTHER), declaration(ME, { content: '문을 연다' })] });
    expect(myDeclaration(current, ME)?.content).toBe('문을 연다');
    expect(myDeclaration(current, OTHER)).toBeUndefined();
  });

  it('마감까지 남은 초. 마감이 없으면 null, 지났으면 0', () => {
    const now = Date.parse('2026-10-22T00:00:00Z');
    expect(remainingSeconds('2026-10-22T00:01:30Z', now)).toBe(90);
    expect(remainingSeconds('2026-10-21T23:59:00Z', now)).toBe(0);
    expect(remainingSeconds(null, now)).toBeNull();
  });
});

describe('declarationForm', () => {
  it('글이 있어야 하고, 판정은 규칙의 능력과 난이도만', () => {
    const empty = initialDeclarationDraft(rules, undefined);
    expect(empty).toEqual({ content: '', withCheck: false, ability: 'str', difficulty: 'normal' });
    expect(declarationHints({ ...empty, content: '  ' }, rules).content).toBeDefined();
    expect(declarationHints({ ...empty, content: '문을 연다', withCheck: true }, rules)).toEqual({});
    expect(declarationHints({ ...empty, content: '문을 연다', withCheck: true, difficulty: 'hell' }, rules).check).toBeDefined();
  });

  it('판정을 붙이면 check 행동을, 안 붙이면 행동 없이 보낸다', () => {
    const draft = { content: '문을 연다', withCheck: true, ability: 'str', difficulty: 'easy' };
    expect(toDeclarationUpdate(draft)).toEqual({
      content: '문을 연다',
      action: { kind: 'check', ability: 'str', difficulty: 'easy', lethal: false },
    });
    expect(toDeclarationUpdate({ ...draft, withCheck: false })).toEqual({ content: '문을 연다' });
  });

  it('낸 판정으로 채우고, 판정이 아닌 행동은 알린다', () => {
    const check = asDeclaration(ME, { content: '민다', action: { kind: 'check', ability: 'con', difficulty: 'easy', lethal: false } });
    expect(initialDeclarationDraft(rules, check)).toEqual({ content: '민다', withCheck: true, ability: 'con', difficulty: 'easy' });
    expect(hasOtherAction(check)).toBe(false);
    expect(hasOtherAction(asDeclaration(ME, { content: '찾는다', action: { kind: 'search' } }))).toBe(true);
  });
});

describe('roundProblem', () => {
  it('마감했으면 알리고 다시 읽는다. 쓰러졌으면 글만 낼 수 있다고 알린다', () => {
    expect(describeDeclarationProblem(new ApiError({ status: 409, detail: 'x', code: 'round_closing' }))).toMatchObject({ refresh: true });
    expect(describeDeclarationProblem(new ApiError({ status: 409, detail: 'x', code: 'character_downed' })).message).toContain('글만');
    expect(describeCloseProblem(new ApiError({ status: 403, detail: 'x' })).message).toBe('방장만 라운드를 닫을 수 있습니다.');
  });
});
