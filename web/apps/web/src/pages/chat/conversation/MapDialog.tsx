// web/apps/web/src/pages/chat/conversation/MapDialog.tsx
// 지도 창(C3). 지금 있는 곳, 바로 갈 수 있는 곳과 걸리는 시간("가기"), 가 본 곳. 가 보지 않은 곳은 이름 옆에 "처음"을 단다.
// 가면 행동 말(이동)이 붙고 그만큼 시각이 흐르며 상대의 반응을 받는다(청구). 갈 수 있는지는 서버가 다시 본다.

import { Button, Dialog } from '@ai-trpg/ui';
import type { ConversationAction, ConversationDetail } from '../../../api/types';
import { placeName } from './conversationView';
import { destinations, minutesLabel, visitedNames } from './worldView';

type Props = { detail: ConversationDetail; open: boolean; busy: boolean; onClose: () => void; onAction: (action: ConversationAction) => void };

export function MapDialog({ detail, open, busy, onClose, onAction }: Props) {
  const document = detail.character.document;
  const here = detail.state.place;
  const ways = destinations(document, detail.state);
  const visited = visitedNames(document, detail.state);
  return (
    <Dialog title="지도" open={open} onClose={onClose}>
      <p>지금 있는 곳: {here ? placeName(document, here) : '정해지지 않음'}</p>
      <h3 className="chat-map__heading">갈 수 있는 곳</h3>
      {ways.length === 0 ? <p className="hint">여기서 바로 이어진 길이 없습니다.</p> : null}
      <ul className="plain-list chat-map" aria-label="갈 수 있는 곳">
        {ways.map((way) => (
          <li key={way.id}>
            <Button variant="secondary" disabled={busy} onClick={() => onAction({ kind: 'move', place: way.id })}>
              {way.name}에 가기
            </Button>{' '}
            <span className="hint">
              {minutesLabel(way.minutes)}
              {way.visited ? '' : ' · 처음'}
            </span>
          </li>
        ))}
      </ul>
      {visited.length > 0 ? <p className="hint">가 본 곳: {visited.join(', ')}</p> : null}
    </Dialog>
  );
}
