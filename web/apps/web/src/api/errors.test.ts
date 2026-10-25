// web/apps/web/src/api/errors.test.ts
// 서버의 실패 응답을 ApiError 로: 입력 오류는 상태 코드가 아니라 errors 로 알아보고, 칸은 errors 안에서 읽는다.

import { describe, expect, it } from 'vitest';
import { describeModerationProblem } from '../pages/operator/moderationProblem';
import { describeSaveProblem } from '../pages/trpg/studio/studioProblem';
import { ApiError, isInputError, toApiError } from './errors';

function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const INVALID = '입력이 올바르지 않습니다.';

describe('toApiError', () => {
  it('FastAPI 서버의 입력 오류(422)는 칸을 errors 에서 읽는다', async () => {
    const error = await toApiError(response(422, { detail: INVALID, errors: { 'action.kind': ['Field required'] } }));

    expect(error.message).toBe(INVALID);
    expect(error.fields).toEqual({ 'action.kind': ['Field required'] });
    expect(isInputError(error)).toBe(true);
  });

  it('게시판과 인증 서버의 입력 오류(400)도 같은 모양으로 읽는다', async () => {
    const error = await toApiError(response(400, { detail: INVALID, errors: { consents: { terms: ['동의해야 합니다.'] } } }));

    expect(error.status).toBe(400);
    expect(error.fields).toEqual({ consents: ['동의해야 합니다.'] });
    expect(isInputError(error)).toBe(true);
  });

  it('입력 칸의 이름이 code 여도 오류의 이름과 섞이지 않는다', async () => {
    const error = await toApiError(response(400, { detail: INVALID, errors: { code: ['6자리 숫자를 적어 주세요.'] } }));

    expect(error.code).toBeUndefined();
    expect(error.fields).toEqual({ code: ['6자리 숫자를 적어 주세요.'] });
  });

  it('code 를 싣는 거절은 입력 오류가 아니다', async () => {
    const error = await toApiError(response(400, { detail: '가입을 처음부터 다시 해 주세요.', code: 'signup_ticket_invalid' }));

    expect(error.code).toBe('signup_ticket_invalid');
    expect(isInputError(error)).toBe(false);
  });

  it('업무의 거절(409 의 used_by)은 입력 오류가 아니다', async () => {
    const error = await toApiError(response(409, { detail: '쓰는 시나리오가 있다', used_by: [{ id: 'a', title: '시험' }] }));

    expect(isInputError(error)).toBe(false);
  });

  it('errors 가 없는 422(서버가 정한 거절)는 입력 오류가 아니다', async () => {
    const error = await toApiError(response(422, { detail: 'narration_model 에 고를 수 없는 값이 있습니다.', field: 'narration_model' }));

    expect(isInputError(error)).toBe(false);
    expect(error.fields).toEqual({});
  });
});

describe('입력 오류를 칸에 보이기', () => {
  const inputError = new ApiError({ status: 422, detail: INVALID, fields: { title: ['String should have at least 1 character'] }, body: { errors: { title: ['String should have at least 1 character'] } } });

  it('제작 도구는 틀린 칸에 까닭을 보인다', () => {
    expect(describeSaveProblem(inputError, 'worlds').fields).toEqual({ title: 'String should have at least 1 character' });
  });

  it('errors 가 없는 422 는 칸 없이 안내만 한다', () => {
    expect(describeSaveProblem(new ApiError({ status: 422, detail: 'x' }), 'worlds').fields).toBeUndefined();
  });

  it('신고 처리는 사유 칸에 까닭을 보인다', () => {
    const reason = new ApiError({ status: 422, detail: INVALID, fields: { reason: ['too long'] }, body: { errors: { reason: ['too long'] } } });

    expect(describeModerationProblem(reason).fields).toEqual({ reason: 'too long' });
  });
});
