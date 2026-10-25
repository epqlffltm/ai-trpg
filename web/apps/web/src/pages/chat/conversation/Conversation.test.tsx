// web/apps/web/src/pages/chat/conversation/Conversation.test.tsx
// 대화(C3). 머리(이름, 장소와 시각, 호감도, 모델), 시작 상황과 말들, 대안 넘기기, 말 보내기와 흘러 들어오는 답(Enter 로 보냄),
// 멈추기, 크레딧 부족(말은 남음), 모델이 없으면 고르기(성인 대화는 성인 모델만), 답 받기·다시 생성·이어서의 주소, 볼 수 없는 대화.
// 흘러 들어오는 답, 대사창, 머리의 글, 실패의 글을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { ConversationMessage } from '../../../api/types';
import { CHARACTER, detail, GEN, ID, M, message, MESSAGES, PATH, posts, saved, signedIn, sse } from '../../../test/chatFixtures';
import { json } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { canSend } from './Composer';
import { affectionView, alternativeView, changeLines, clockLabel, pictureOf, tailActions } from './conversationView';
import { modelLine } from './modelView';
import { describeTurnProblem } from './turnProblem';
import { applyTurnMessage, EMPTY_TURN, failedText } from './turnState';
import { visibleMessages } from './visibleMessages';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('대화', () => {
  it('머리와 시작 상황, 말들을 보이고, 대안을 넘기면 바뀐 가지를 그린다', async () => {
    const { seen } = signedIn({
      [`PUT ${PATH}/branch`]: () => json(200, detail({ messages: [...MESSAGES.slice(0, 2), message(3, 'assistant', '다른 답이에요.', { id: M(9), alternatives: [M(3), M(9)] })] })),
    });
    renderApp(`/chat/conversations/${ID}`);

    expect(await screen.findByRole('link', { name: '루나' })).toHaveAttribute('href', `/chat/characters/${CHARACTER}`);
    expect(screen.getByText('카페 · 1일째 낮 15:30')).toBeInTheDocument();
    expect(screen.getByText('호감: 친구(2/4)')).toBeInTheDocument();
    expect(screen.getByText(/모델: GLM/)).toBeInTheDocument();
    expect(screen.getByText('비를 피해 카페에 들어온다.')).toBeInTheDocument();
    const log = within(screen.getByRole('list', { name: '말' }));
    expect(log.getByText('비가 오네요.')).toBeInTheDocument();
    expect(log.getByText('호감이 올랐다')).toBeInTheDocument();
    expect(log.getByText('1/2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '우산 있어?' })).toBeInTheDocument();

    await userEvent.click(log.getByRole('button', { name: '뒤의 대안' }));
    expect(await log.findByText('다른 답이에요.')).toBeInTheDocument();
    expect(posts(seen, `${PATH}/branch`).map((request) => request.body)).toEqual([{ message_id: M(9) }]);
  });

  it('추천을 눌러 채우고 Enter 로 보내면 답이 흘러 들어오고, 끝나면 저장된 대화를 다시 읽는다', async () => {
    let after = false;
    const { seen } = signedIn(
      {
        [`POST ${PATH}/messages`]: () => {
          after = true;
          return new Response(
            sse(['turn', { generation_id: GEN, user_message: saved(4, 'user', '우산 있어?'), continues: null, action: null }], ['delta', { text: '있어요, ' }], ['delta', { text: '같이 써요.' }], ['done', { message: saved(5, 'assistant', '있어요, 같이 써요.') }]),
            { headers: { 'Content-Type': 'text/event-stream' } },
          );
        },
      },
      () => (after ? detail({ messages: [...MESSAGES, message(4, 'user', '우산 있어?'), message(5, 'assistant', '있어요, 같이 써요.')] }) : detail()),
    );
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '우산 있어?' }));
    const box = screen.getByRole('textbox', { name: '보낼 말' });
    expect(box).toHaveValue('우산 있어?');
    await userEvent.type(box, '{Enter}');

    expect(await screen.findByText('있어요, 같이 써요.')).toBeInTheDocument();
    expect(box).toHaveValue('');
    expect(posts(seen, `${PATH}/messages`).map((request) => request.body)).toEqual([{ content: '우산 있어?' }]);
    await vi.waitFor(() => expect(seen.filter((request) => request.url === PATH).length).toBeGreaterThan(1));
  });

  it('받는 중에는 멈추기만 누를 수 있고, 멈추면 청구하지 않았다고 알린다', async () => {
    let push: (text: string) => void = () => undefined;
    let close: () => void = () => undefined;
    const { seen } = signedIn({
      [`POST ${PATH}/messages`]: () => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            const encoder = new TextEncoder();
            push = (text) => controller.enqueue(encoder.encode(text));
            close = () => controller.close();
          },
        });
        queueMicrotask(() => push(sse(['turn', { generation_id: GEN, user_message: saved(4, 'user', '안녕?'), continues: null, action: null }])));
        return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
      },
      [`POST /api/v1/chat/generations/${GEN}/stop`]: () => {
        push(sse(['failed', { code: 'stopped' }]));
        close();
        return new Response(null, { status: 204 });
      },
    });
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.type(await screen.findByRole('textbox', { name: '보낼 말' }), '안녕?{Enter}');
    const stop = await screen.findByRole('button', { name: '멈추기' });
    await vi.waitFor(() => expect(stop).toBeEnabled());
    expect(screen.getByRole('button', { name: '보내기' })).toBeDisabled();
    expect(screen.getByText('안녕?')).toBeInTheDocument();

    await userEvent.click(stop);
    expect(await screen.findByText(/받은 글이 없어 청구하지 않았습니다/)).toBeInTheDocument();
    expect(posts(seen, `/api/v1/chat/generations/${GEN}/stop`)).toHaveLength(1);
    expect(screen.queryByRole('button', { name: '멈추기' })).toBeNull();
  });

  it('크레딧이 모자라면 말은 남았다고 알리고 충전으로 가는 길을 보인다', async () => {
    signedIn({ [`POST ${PATH}/messages`]: () => json(402, { detail: '모자람', code: 'credit_short', message_id: M(4) }) });
    renderApp(`/chat/conversations/${ID}`);

    const box = await screen.findByRole('textbox', { name: '보낼 말' });
    await userEvent.type(box, '안녕?');
    await userEvent.click(screen.getByRole('button', { name: '보내기' }));
    expect(await screen.findByText(/크레딧이 모자랍니다. 보낸 말은 남았습니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '충전하기' })).toHaveAttribute('href', '/wallet/charge');
    expect(box).toHaveValue('');
  });

  it('모델이 없으면 보내기 전에 고르게 한다. 성인 대화에는 성인 모델만 보인다', async () => {
    const { seen } = signedIn(
      {
        'GET /api/v1/chat/models': () =>
          json(200, {
            free: false,
            items: [
              { slug: 'glm', display_name: 'GLM', vendor: 'zai', grade: 'standard', allows_adult: true, retires_on: null, credits: '80', tier: 'standard', promo: false, next: null },
              { slug: 'flash', display_name: 'Flash', vendor: 'gemini', grade: 'standard', allows_adult: false, retires_on: null, credits: '90', tier: 'standard', promo: false, next: null },
            ],
          }),
        [`PUT ${PATH}/model`]: () => json(200, { slug: 'glm', display_name: 'GLM', vendor: 'zai', grade: 'standard', retires_on: null, usable: true }),
      },
      () => detail({ model: null, character: { ...detail().character, rating: 'adult' } }),
    );
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.type(await screen.findByRole('textbox', { name: '보낼 말' }), '안녕?');
    await userEvent.click(screen.getByRole('button', { name: '보내기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '모델 고르기' }));
    expect(await dialog.findByRole('radio', { name: 'GLM' })).toBeInTheDocument();
    expect(dialog.queryByRole('radio', { name: 'Flash' })).toBeNull();
    expect(dialog.getByText('표준 · 말 한 번 80 크레딧')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('radio', { name: 'GLM' }));
    await userEvent.click(dialog.getByRole('button', { name: '이 모델로 하기' }));

    expect(await screen.findByText(/모델: GLM/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(posts(seen, `${PATH}/model`).map((request) => request.body)).toEqual([{ model: 'glm' }]);
    expect(screen.getByRole('textbox', { name: '보낼 말' })).toHaveValue('안녕?');
  });

  it('끝이 사람의 말이면 답 받기, 끊긴 답이면 이어서와 다시 생성. 각 주소로 부른다', async () => {
    const done = () => new Response(sse(['failed', { code: 'empty' }]), { headers: { 'Content-Type': 'text/event-stream' } });
    const { seen } = signedIn(
      {
        [`POST /api/v1/chat/messages/${M(3)}/continue`]: done,
        [`POST /api/v1/chat/messages/${M(3)}/regenerate`]: done,
      },
      () => detail({ messages: [MESSAGES[0] as ConversationMessage, MESSAGES[1] as ConversationMessage, { ...(MESSAGES[2] as ConversationMessage), status: 'partial' }] }),
    );
    renderApp(`/chat/conversations/${ID}`);

    expect(await screen.findByText(/끊긴 답/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '이어서' }));
    expect(await screen.findByText(/빈 답을 냈습니다. 청구하지 않았습니다/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: '다시 생성' }));
    await vi.waitFor(() => expect(posts(seen, `/api/v1/chat/messages/${M(3)}/regenerate`)).toHaveLength(1));
    expect(posts(seen, `/api/v1/chat/messages/${M(3)}/continue`)).toHaveLength(1);
  });

  it('볼 수 없는 대화면 까닭과 탐색으로 가는 길', async () => {
    signedIn({ [`GET ${PATH}`]: () => json(404, { detail: 'x' }) });
    renderApp(`/chat/conversations/${ID}`);
    expect(await screen.findByText(/볼 수 없는 대화입니다/)).toBeInTheDocument();
  });
});

describe('대화의 순수한 함수', () => {
  it('흘러 들어오는 답과 대사창', () => {
    let state = applyTurnMessage(EMPTY_TURN, { event: 'turn', data: JSON.stringify({ generation_id: GEN, user_message: saved(4, 'user', '안녕?'), continues: null }) });
    state = applyTurnMessage(state, { event: 'expression', data: '{"expression":"웃음","sprite":"s1"}' });
    state = applyTurnMessage(state, { event: 'delta', data: '{"text":"반가워"}' });
    state = applyTurnMessage(state, { event: 'delta', data: 'not json' });
    expect(state).toMatchObject({ generationId: GEN, text: '반가워', sprite: 's1', end: null });
    expect(visibleMessages(MESSAGES, state).items).toHaveLength(4);
    expect(visibleMessages(MESSAGES, state).pending).toBe('반가워');
    const regenerating = { ...state, userMessage: saved(2, 'user', '안녕') };
    expect(visibleMessages(MESSAGES, regenerating).items.map((item) => item.message.id)).toEqual([M(1), M(2)]);
    const continuing = { ...state, userMessage: saved(2, 'user', '안녕'), continues: M(3) };
    expect(visibleMessages(MESSAGES, continuing).items[2]?.message.content).toBe('비가 오네요.반가워');
    const failed = applyTurnMessage(state, { event: 'failed', data: '{"code":"timeout"}' });
    expect(failed.end).toEqual({ kind: 'failed', code: 'timeout' });
    expect(applyTurnMessage(failed, { event: 'delta', data: '{"text":"늦은 글"}' })).toBe(failed);
    expect(failedText('timeout')).toContain('청구하지 않았습니다');
  });

  it('머리와 말의 글, 끝에서 할 일, 그림', () => {
    expect(clockLabel({ day: 2, hour: 8, minute: 5, time_of_day: 'morning' })).toBe('2일째 아침 08:05');
    expect(affectionView({ display: 'number', value: 37, stage: '아는 사이', stage_index: 0, stages: 3 })).toEqual({ label: '호감 37/100', percent: 37 });
    expect(affectionView(null)).toBeNull();
    const document = { places: [{ id: 'park', name: '공원', description: '', image_id: null }], items: [{ id: 'rose', name: '장미', description: '', kind: 'gift', image_id: null }] } as never;
    expect(changeLines([{ kind: 'affection', rising: false, delta: -2 }, { kind: 'gift', item: 'rose' }, { kind: 'move', place: 'park', minutes: 15 }], document)).toEqual(['호감이 내렸다(-2)', '장미을(를) 받았다', '공원에 함께 갔다(15분)']);
    expect(alternativeView({ id: 'b', alternatives: ['a', 'b', 'c'] })).toEqual({ position: 2, count: 3, previous: 'a', next: 'c' });
    expect(alternativeView({ id: 'a', alternatives: ['a'] })).toBeNull();
    expect(tailActions(MESSAGES.slice(0, 2))).toEqual({ answer: M(2), regenerate: null, continueFrom: null });
    expect(tailActions(MESSAGES.slice(0, 1))).toEqual({ answer: null, regenerate: null, continueFrom: null });
    const withScene = detail({
      messages: [message(1, 'assistant', '어서 와요.'), message(2, 'action', '공원에 갔다.', { event_scene: 'rain' }), message(3, 'assistant', '비가 와요.')],
      character: { ...detail().character, document: { ...detail().character.document, event_scenes: [{ id: 'rain', title: '비 오는 공원', image_id: 'img-rain', when: { kind: 'reach_place', target: 'park' } }] } } as never,
    });
    expect(pictureOf(withScene, null).scene).toEqual({ title: '비 오는 공원', imageId: 'img-rain' });
    expect(pictureOf(detail(), { answering: null, sprite: 'sp' }).sprite).toBe('sp');
  });

  it('거절의 글과 할 일, 모델의 한 줄, 보낼 수 있는 말', () => {
    expect(describeTurnProblem(new ApiError({ status: 409, detail: 'x', code: 'model_required' }))).toMatchObject({ chooseModel: true });
    expect(describeTurnProblem(new ApiError({ status: 402, detail: 'x', code: 'gold_required', body: { message_id: 'm' } }))).toMatchObject({ charge: true, reload: true });
    expect(describeTurnProblem(new ApiError({ status: 429, detail: 'x', code: 'too_many_attempts', retryAfter: 9 })).text).toContain('9초 뒤에');
    expect(describeTurnProblem(new ApiError({ status: 503, detail: 'x', code: 'provider_unavailable', retryAfter: 5 })).text).toContain('5초 뒤에');
    expect(modelLine({ slug: 'x', display_name: 'X', vendor: 'v', grade: 'premium', allows_adult: false, retires_on: '2026-12-21', credits: '300', tier: 'premium', promo: true, next: { credits: null, tier: null, promo: false, effective_at: '2026-12-01T00:00:00Z' } })).toBe(
      '프리미엄 · 말 한 번 300 크레딧 · 골드로만 · 행사가 · 12월 1일부터 팔지 않음 · 12월 21일 종료',
    );
    expect(canSend('  ')).toBe(false);
    expect(canSend('가')).toBe(true);
    expect(canSend('가'.repeat(4001))).toBe(false);
  });
});
