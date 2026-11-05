// web/apps/web/src/pages/chat/conversation/ChatTools.tsx
// 대화(C3)의 왼쪽 열 창 넷(Stitch 21번). 단추가 세로로 서고, 누른 단추 바로 아래로 그 창이 펼쳐진다(테이블 방의 창 넷과 같은 모양).
// 창은 하나만 펼친다. 펼친 단추를 다시 누르면 접는다. 처음에는 맨 앞의 창이 펼쳐져 있다.
//   - 지도·이동: 지금 있는 곳, 갈 수 있는 곳과 "가기"(판에 지도가 있을 때만)
//   - 소지품·건네기: 가진 물건, 쓰기와 건네기
//   - 상대의 차림·기억: 지금 입은 옷, 기억 메모(펼친 동안만 읽는다)와 앞부분의 요약
//   - 페르소나·모델: 지금의 페르소나, 지금의 모델과 "모델 바꾸기"(고르는 창은 ConversationRoom 이 연다)
// 행동(가기, 쓰기, 건네기)은 반응을 받으므로 받는 중이면 막는다(busy). 창을 펼치는 것과 기억 고치기는 막지 않는다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ConversationAction, ConversationDetail } from '../../../api/types';
import { retireText } from '../../trpg/models/modelChoice';
import { InventoryPanel } from './InventoryPanel';
import { MapPanel } from './MapPanel';
import { ChatNotes } from './NotesDialog';
import { OutfitPanel } from './OutfitPanel';
import { hasMap } from './worldView';

export type ChatTool = 'map' | 'items' | 'partner' | 'persona';

const TOOL_LABELS: Record<ChatTool, string> = {
  map: '지도·이동',
  items: '소지품·건네기',
  partner: '상대의 차림·기억',
  persona: '페르소나·모델',
};

/** 이 대화에 있는 창. 지도는 판에 지도가 있을 때만 */
export function chatTools(withMap: boolean): ChatTool[] {
  return withMap ? ['map', 'items', 'partner', 'persona'] : ['items', 'partner', 'persona'];
}

type Props = {
  detail: ConversationDetail;
  busy: boolean;
  onAction: (action: ConversationAction) => void;
  onChooseModel: () => void;
};

export function ChatTools({ detail, busy, onAction, onChooseModel }: Props) {
  const tools = chatTools(hasMap(detail.character.document));
  const [open, setOpen] = useState<ChatTool | null>(tools[0] ?? null);
  return (
    <section className="room-tools" aria-labelledby="chat-tools-heading">
      <h2 id="chat-tools-heading" className="visually-hidden">
        창
      </h2>
      {tools.map((tool) => (
        <div key={tool} className="room-tools__item">
          <button
            type="button"
            id={`chat-tool-${tool}`}
            className="room-tools__button"
            aria-expanded={open === tool}
            aria-controls={`chat-tool-panel-${tool}`}
            onClick={() => setOpen((current) => (current === tool ? null : tool))}
          >
            {TOOL_LABELS[tool]}
          </button>
          {open === tool ? (
            <div id={`chat-tool-panel-${tool}`} role="region" aria-labelledby={`chat-tool-${tool}`} className="room-tools__panel">
              <ToolContent tool={tool} detail={detail} busy={busy} onAction={onAction} onChooseModel={onChooseModel} />
            </div>
          ) : null}
        </div>
      ))}
    </section>
  );
}

function ToolContent({ tool, detail, busy, onAction, onChooseModel }: Props & { tool: ChatTool }) {
  if (tool === 'map') return <MapPanel detail={detail} busy={busy} onAction={onAction} />;
  if (tool === 'items') return <InventoryPanel detail={detail} busy={busy} onAction={onAction} />;
  if (tool === 'partner') {
    return (
      <>
        <OutfitPanel detail={detail} />
        <ChatNotes conversationId={detail.id} name={detail.character.document.name} />
      </>
    );
  }
  return <PersonaModel detail={detail} busy={busy} onChooseModel={onChooseModel} />;
}

/** 페르소나·모델. 페르소나는 대화를 시작할 때 정해져 여기서는 보기만 한다 */
function PersonaModel({ detail, busy, onChooseModel }: { detail: ConversationDetail; busy: boolean; onChooseModel: () => void }) {
  return (
    <div className="chat-persona">
      <dl>
        <div>
          <dt>페르소나</dt>
          <dd>{detail.persona ? detail.persona.name : '고르지 않음'}</dd>
        </div>
        <div>
          <dt>모델</dt>
          <dd>
            {detail.model ? detail.model.display_name : '고르지 않음'}
            {detail.model?.retires_on ? <span className="hint"> · {retireText(detail.model.retires_on)}</span> : null}
          </dd>
        </div>
      </dl>
      <Button variant="secondary" disabled={busy} onClick={onChooseModel}>
        {detail.model ? '모델 바꾸기' : '모델 고르기'}
      </Button>
    </div>
  );
}
