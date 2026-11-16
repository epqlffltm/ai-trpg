// web/apps/web/src/api/stepUpGate.test.ts
// 본인 확인이 필요하다는 답(403)이면 확인을 받고 한 번 다시 보내는지, 닫으면 처음 답을 던지는지,
// 여러 작업이 한꺼번에 요구해도 창을 한 번만 띄우는지, 띄울 자리가 없으면 묻지 않는지 본다.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './errors';
import { askStepUp, isStepUpRequired, setStepUpAsker, withStepUp } from './stepUpGate';

const REQUIRED = new ApiError({ status: 403, detail: 'x', code: 'step_up.required' });

let clear: (() => void) | null = null;

function install(asker: () => Promise<boolean>) {
  clear = setStepUpAsker(asker);
}

afterEach(() => {
  clear?.();
  clear = null;
});

describe('withStepUp', () => {
  it('통과하면 묻지 않는다', async () => {
    const asker = vi.fn(async () => true);
    install(asker);

    await expect(withStepUp(async () => 'ok')).resolves.toBe('ok');
    expect(asker).not.toHaveBeenCalled();
  });

  it('확인이 필요하면 확인을 받고 한 번 다시 부른다', async () => {
    install(async () => true);
    const call = vi.fn().mockRejectedValueOnce(REQUIRED).mockResolvedValueOnce('ok');

    await expect(withStepUp(call)).resolves.toBe('ok');
    expect(call).toHaveBeenCalledTimes(2);
  });

  it('확인 창을 닫으면 다시 부르지 않고 처음 답을 던진다', async () => {
    install(async () => false);
    const call = vi.fn().mockRejectedValue(REQUIRED);

    await expect(withStepUp(call)).rejects.toBe(REQUIRED);
    expect(call).toHaveBeenCalledOnce();
  });

  it('다시 불러도 확인이 필요하면 또 묻지 않는다', async () => {
    const asker = vi.fn(async () => true);
    install(asker);
    const call = vi.fn().mockRejectedValue(REQUIRED);

    await expect(withStepUp(call)).rejects.toBe(REQUIRED);
    expect(asker).toHaveBeenCalledOnce();
    expect(call).toHaveBeenCalledTimes(2);
  });

  it('다른 실패는 그대로 던진다', async () => {
    const asker = vi.fn(async () => true);
    install(asker);
    const disabled = new ApiError({ status: 403, detail: 'x', code: 'step_up.disabled' });

    await expect(withStepUp(() => Promise.reject(disabled))).rejects.toBe(disabled);
    expect(asker).not.toHaveBeenCalled();
  });
});

describe('askStepUp', () => {
  it('한꺼번에 여러 번 물어도 창은 한 번이다', async () => {
    let answer: (verified: boolean) => void = () => {};
    const asker = vi.fn(() => new Promise<boolean>((resolve) => (answer = resolve)));
    install(asker);

    const first = askStepUp();
    const second = askStepUp();
    answer(true);

    await expect(Promise.all([first, second])).resolves.toEqual([true, true]);
    expect(asker).toHaveBeenCalledOnce();
  });

  it('띄울 자리가 없으면 false 다', async () => {
    await expect(askStepUp()).resolves.toBe(false);
  });

  it('치운 자리는 다시 부르지 않는다', async () => {
    const asker = vi.fn(async () => true);
    install(asker);
    clear?.();

    await expect(askStepUp()).resolves.toBe(false);
    expect(asker).not.toHaveBeenCalled();
  });
});

describe('isStepUpRequired', () => {
  it('결제 서버와 인증 서버의 403 을 알아본다', () => {
    expect(isStepUpRequired(REQUIRED)).toBe(true);
    expect(isStepUpRequired(new ApiError({ status: 403, detail: 'x', code: 'step_up_required' }))).toBe(true);
    expect(isStepUpRequired(new ApiError({ status: 403, detail: 'x', code: 'payment.verification_required' }))).toBe(false);
    expect(isStepUpRequired(new ApiError({ status: 409, detail: 'x', code: 'step_up.required' }))).toBe(false);
    expect(isStepUpRequired(new Error('x'))).toBe(false);
  });
});
