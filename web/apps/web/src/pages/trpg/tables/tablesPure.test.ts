// web/apps/web/src/pages/trpg/tables/tablesPure.test.ts
// 테이블 만들기의 입력과 테이블 화면의 실패를 순수한 함수로 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { PublicListingDetail } from '../../../api/types';
import { durationLabel } from '../labels';
import { tableFacts } from '../lobby/LobbyCard';
import { draftHints, initialDraft, toTableCreate } from './createForm';
import { modelOptionLabel } from './ModelSelect';
import { describeCreateProblem, describeJoinProblem, optionField } from './tableProblem';

const LISTING = {
  scenario_id: 's-1',
  recommended_players: { min: 2, max: 3 },
  character_modes: ['pregen', 'custom'],
  references_allowed: false,
} as unknown as PublicListingDetail;

function apiError(status: number, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({ status, detail: '서버의 글', ...extra });
}

describe('createForm', () => {
  it('처음 값으로 보내면 비운 것은 서버가 시나리오의 것을 쓴다', () => {
    expect(toTableCreate(initialDraft(LISTING), LISTING)).toEqual({
      scenario_id: 's-1',
      opening_index: 0,
      capacity: 3,
      is_public: false,
      password: null,
      character_modes: null,
      narration_style: null,
      round_time_limit: 300,
      narration_model: null,
      credit_wait_seconds: 300,
      remove_short_payers: true,
      whisper_notice: false,
      references_enabled: false,
    });
  });

  it('비공개면 비밀번호를 보내지 않고, 좁힌 캐릭터 방식만 보낸다', () => {
    const draft = { ...initialDraft(LISTING), password: 'secret', characterModes: ['custom' as const] };
    const body = toTableCreate(draft, LISTING);
    expect(body.password).toBeNull();
    expect(body.character_modes).toEqual(['custom']);
    expect(toTableCreate({ ...draft, isPublic: true }, LISTING).password).toBe('secret');
  });

  it('허용하지 않은 참고 자료는 켜도 보내지 않는다', () => {
    expect(toTableCreate({ ...initialDraft(LISTING), referencesEnabled: true }, LISTING).references_enabled).toBe(false);
  });

  it('비밀번호의 길이와 캐릭터 방식이 비었는지를 보내기 전에 알린다', () => {
    const draft = { ...initialDraft(LISTING), isPublic: true, password: 'abc', characterModes: [] };
    expect(Object.keys(draftHints(draft)).sort()).toEqual(['character_modes', 'password']);
    expect(draftHints(initialDraft(LISTING))).toEqual({});
  });
});

describe('tableProblem', () => {
  it('비밀번호가 틀리면 칸에, 성인용이면 인증으로 안내한다', () => {
    expect(describeJoinProblem(apiError(403)).fields).toEqual({ password: '비밀번호가 맞지 않습니다.' });
    expect(describeJoinProblem(apiError(403, { code: 'adult_content_required' })).message).toMatch(/성인 확인/);
  });

  it('409 의 까닭으로 목록을 다시 읽거나 그 테이블로 간다', () => {
    expect(describeJoinProblem(apiError(409, { code: 'table_full' }))).toMatchObject({ refresh: true });
    expect(describeJoinProblem(apiError(409, { code: 'not_recruiting' }))).toMatchObject({ refresh: true });
    expect(describeJoinProblem(apiError(409, { code: 'already_seated' }))).toMatchObject({ seated: true });
  });

  it('너무 많이 틀리면 기다리게 한다', () => {
    expect(describeJoinProblem(apiError(429, { retryAfter: 40 }))).toMatchObject({ waitSeconds: 40 });
  });

  it('만들 때 모델을 쓸 수 없으면 모델 칸에 알린다', () => {
    const problem = describeCreateProblem(apiError(422, { detail: 'narration_model 에 고를 수 없는 값이 있습니다.' }));
    expect(problem.fields?.narration_model).toMatch(/서술 모델을 골라/);
    expect(optionField('opening_index 에 고를 수 없는 값이 있습니다.')).toBe('opening_index');
    expect(optionField('다른 글')).toBeNull();
  });
});

describe('labels', () => {
  it('시간을 글로 바꾼다', () => {
    expect(durationLabel(300)).toBe('5분');
    expect(durationLabel(3600)).toBe('1시간');
    expect(durationLabel(45)).toBe('45초');
    expect(durationLabel(null)).toBe('제한 없음');
  });

  it('모델의 고를 거리에 묶음과 값을 붙인다', () => {
    const model = { grade: 'premium', display_name: 'Claude', credits: '120', tier: 'premium' };
    expect(modelOptionLabel(model as never)).toBe('프리미엄 · Claude · 120 크레딧(골드만)');
    expect(modelOptionLabel({ ...model, credits: null } as never)).toBe('프리미엄 · Claude');
  });

  it('로비의 카드는 켜진 설정만 적는다', () => {
    const table = {
      rating: 'all',
      has_password: true,
      narration_style: 'classic',
      round_time_limit: null,
      credit_wait_seconds: 300,
      remove_short_payers: false,
      whisper_notice: false,
      references_enabled: false,
    };
    expect(tableFacts(table as never, null)).toEqual([
      '비밀번호',
      '문체 정통',
      '라운드 제한 없음',
      '크레딧 기다림 5분(빼지 않음)',
    ]);
  });
});
