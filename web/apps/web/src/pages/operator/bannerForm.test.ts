// web/apps/web/src/pages/operator/bannerForm.test.ts
// 운영자의 배너 걸기(#994): 서버의 규칙(차례 0~999, 끝은 시작보다 뒤)을 미리 보고, 서버마다 보낼 모양으로 바꾼다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../api/errors';
import { bannerHints, canHang, describeBannerProblem, EMPTY_BANNER, toAssetBody, toScenarioBody } from './bannerForm';

const ID = '00000000-0000-4000-8000-0000000000a1';

describe('bannerForm', () => {
  it('작품 ID, 차례, 기간을 미리 본다', () => {
    expect(bannerHints({ ...EMPTY_BANNER, targetId: 'abc' }).targetId).toContain('작품의 ID');
    expect(bannerHints({ ...EMPTY_BANNER, position: '1000' }).position).toBe('0~999 사이의 정수입니다.');
    expect(bannerHints({ ...EMPTY_BANNER, startsAt: '2026-11-02T10:00', endsAt: '2026-11-02T09:00' }).endsAt).toBe('끝은 시작보다 뒤여야 합니다.');
    expect(canHang(EMPTY_BANNER)).toBe(false);
    expect(canHang({ ...EMPTY_BANNER, targetId: ID })).toBe(true);
  });

  it('서버마다 보낼 모양. 비운 기간은 보내지 않는다', () => {
    expect(toScenarioBody({ ...EMPTY_BANNER, targetId: ` ${ID} `, position: '3' })).toEqual({ scenario_id: ID, position: 3 });
    const world = toAssetBody({ ...EMPTY_BANNER, target: 'world', targetId: ID, endsAt: '2026-11-02T09:00' });
    expect(world).toMatchObject({ kind: 'world', target_id: ID, position: 0 });
    expect(world.ends_at).toBe(new Date('2026-11-02T09:00').toISOString());
    expect(world).not.toHaveProperty('starts_at');
  });

  it('409 는 공개 목록에 나오지 않는 작품이다', () => {
    const error = new ApiError({ status: 409, detail: 'x', body: { code: 'not_published' } });

    expect(describeBannerProblem(error).message).toContain('공개 목록에 나오는 작품만');
  });
});
