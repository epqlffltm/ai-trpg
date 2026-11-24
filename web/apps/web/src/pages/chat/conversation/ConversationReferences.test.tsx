// web/apps/web/src/pages/chat/conversation/ConversationReferences.test.tsx
// 대화(C3)의 참고 자료 쓰기(#1338). 왼쪽 열의 페르소나·모델 창에 있다. 캐릭터가 허용했을 때만 보이고,
// 켜고 끄면 PUT /references 를 보내고 읽어 둔 대화의 칸만 바꾼다. 허용하지 않았다는 답(422)은 까닭을 적는다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ConversationDetail } from '../../../api/types';
import { json } from '../../../test/fakeFetch';
import { detail, ID, PATH, posts, signedIn } from '../../../test/chatFixtures';
import { renderApp } from '../../../test/renderApp';

const REFERENCES = `${PATH}/references`;

function allowing(enabled: boolean): ConversationDetail {
  const base = detail();
  return { ...base, references_enabled: enabled, character: { ...base.character, document: { ...base.character.document, references_allowed: true } } };
}

async function personaPanel() {
  const column = within(await screen.findByRole('region', { name: '창' }));
  await userEvent.click(column.getByRole('button', { name: '페르소나·모델' }));
  return within(column.getByRole('region', { name: '페르소나·모델' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('대화의 참고 자료', () => {
  it('허용한 캐릭터면 켜고 끈다', async () => {
    const { seen } = signedIn({ [`PUT ${REFERENCES}`]: (request) => json(200, request.body) }, () => allowing(false));
    renderApp(`/chat/conversations/${ID}`);

    const panel = await personaPanel();
    const toggle = panel.getByRole('checkbox', { name: '참고 자료 쓰기' });
    expect(toggle).not.toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());

    expect(posts(seen, REFERENCES).map((request) => request.body)).toEqual([{ enabled: true }, { enabled: false }]);
  });

  it('허용하지 않은 캐릭터면 보이지 않는다', async () => {
    signedIn();
    renderApp(`/chat/conversations/${ID}`);

    const panel = await personaPanel();
    expect(panel.getByRole('button', { name: '모델 바꾸기' })).toBeInTheDocument();
    expect(panel.queryByRole('checkbox', { name: '참고 자료 쓰기' })).toBeNull();
  });

  it('서버가 허용하지 않았다고 하면 까닭을 적고 그대로 둔다', async () => {
    signedIn(
      { [`PUT ${REFERENCES}`]: () => json(422, { detail: '이 캐릭터는 참고 자료를 쓸 수 없습니다.', code: 'references_not_allowed' }) },
      () => allowing(false),
    );
    renderApp(`/chat/conversations/${ID}`);

    const panel = await personaPanel();
    await userEvent.click(panel.getByRole('checkbox', { name: '참고 자료 쓰기' }));

    expect(await panel.findByText('만든 사람이 참고 자료를 허용하지 않았습니다.')).toBeInTheDocument();
    expect(panel.getByRole('checkbox', { name: '참고 자료 쓰기' })).not.toBeChecked();
  });
});
