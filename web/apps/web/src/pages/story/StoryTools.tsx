// web/apps/web/src/pages/story/StoryTools.tsx
// 장면(D2)의 왼쪽 열 창(Stitch 22번). 단추가 세로로 서고, 누른 단추 바로 아래로 그 창이 펼쳐진다(테이블 방, chat 의 창과 같은 모양).
// 창은 하나만 펼친다. 펼친 단추를 다시 누르면 접는다. 펼친 창은 StoryRoom 이 쥔다(좁은 화면의 아래 단추 줄도 같은 창을 펼친다).
//   - 지도·이동: 지금 있는 곳과 갈 수 있는 곳(시간이 흐르는 판에만, 끝난 세션에는 없다)
//   - 소지품·건네기: 가진 물건(건네기는 인물 메뉴에서)
//   - 인물: 세계관의 인물 목록과 고른 인물의 그림, 이름, 인물 창(D5)
//   - 기록: 엔딩과 열린 이벤트(펼친 동안만 읽는다)
//   - 기억: 기억 메모와 앞부분의 요약(펼친 동안만 읽는다)
//   - 페르소나·모델: 지금의 페르소나와 모델, 바꾸기(StoryPersonaPanel)
// 건네기와 고백은 장면의 인물을 눌러 연다.

import type { StoryAction, StorySession, StoryState, StoryView } from '../../api/story';
import { canPassTime } from './storyActions';
import { StoryCastPanel } from './StoryCastPanel';
import { StoryItemsPanel } from './StoryItemsPanel';
import { StoryMapPanel } from './StoryMapPanel';
import { StoryNotesPanel } from './StoryNotesPanel';
import { StoryPersonaPanel } from './StoryPersonaPanel';
import { StoryRecordsPanel } from './StoryRecordsPanel';

export type StoryTool = 'map' | 'items' | 'cast' | 'records' | 'notes' | 'persona';

const TOOL_LABELS: Record<StoryTool, string> = {
  map: '지도·이동',
  items: '소지품·건네기',
  cast: '인물',
  records: '기록',
  notes: '기억',
  persona: '페르소나·모델',
};

/** 창의 이름(단추의 글) */
export function storyToolLabel(tool: StoryTool): string {
  return TOOL_LABELS[tool];
}

/** 이 장면에 있는 창. 지도·이동은 시간이 흐르는 판이고 끝나지 않았을 때만 */
export function storyTools(withMap: boolean): StoryTool[] {
  return withMap ? ['map', 'items', 'cast', 'records', 'notes', 'persona'] : ['items', 'cast', 'records', 'notes', 'persona'];
}

/** 지도·이동을 둘지. 시간이 흐르는 판이고 끝나지 않은 세션 */
export function storyHasMap(view: StoryView, state: StoryState, ended: boolean): boolean {
  return !ended && canPassTime(view, state);
}

type Props = {
  session: StorySession;
  /** 장면의 상태(받는 중이면 흘러 들어온 값) */
  state: StoryState;
  tools: StoryTool[];
  disabled: boolean;
  onAct: (action: StoryAction) => Promise<boolean>;
  /** 모델을 고르는 창을 연다(StoryRoom 이 쥔다) */
  onChooseModel: () => void;
  open: StoryTool | null;
  onOpenChange: (next: StoryTool | null) => void;
};

export function StoryTools({ tools, open, onOpenChange, ...rest }: Props) {
  return (
    <section className="room-tools" aria-labelledby="story-tools-heading">
      <h2 id="story-tools-heading" className="visually-hidden">
        창
      </h2>
      {tools.map((tool) => (
        <div key={tool} className="room-tools__item">
          <button
            type="button"
            id={`story-tool-${tool}`}
            className="room-tools__button"
            aria-expanded={open === tool}
            aria-controls={`story-tool-panel-${tool}`}
            onClick={() => onOpenChange(open === tool ? null : tool)}
          >
            {TOOL_LABELS[tool]}
          </button>
          {open === tool ? (
            <div id={`story-tool-panel-${tool}`} role="region" aria-labelledby={`story-tool-${tool}`} className="room-tools__panel">
              <ToolContent tool={tool} {...rest} />
            </div>
          ) : null}
        </div>
      ))}
    </section>
  );
}

type ContentProps = Omit<Props, 'tools' | 'open' | 'onOpenChange'> & { tool: StoryTool };

function ToolContent({ tool, session, state, disabled, onAct, onChooseModel }: ContentProps) {
  const view = session.view;
  if (tool === 'map') return <StoryMapPanel view={view} state={state} disabled={disabled} onAct={onAct} />;
  if (tool === 'items') return <StoryItemsPanel view={view} state={state} />;
  if (tool === 'cast') return <StoryCastPanel view={view} state={state} />;
  if (tool === 'records') return <StoryRecordsPanel worldId={session.world.id} view={view} />;
  if (tool === 'notes') return <StoryNotesPanel sessionId={session.id} />;
  return <StoryPersonaPanel session={session} disabled={disabled} onChooseModel={onChooseModel} />;
}
