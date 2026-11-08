// web/apps/web/src/pages/trpg/room/RoomTalk.tsx
// 테이블 방 맨 아래의 대화창(Stitch 20번). 위에 탭 셋 "채팅", "쪽지", "주사위"(#404)를 두고 고른 탭의 칸
// (ChatPanel, WhisperPanel, DicePanel)을 보인다.
// 안 읽은 쪽지가 있으면 쪽지 탭에 수를 띄운다. 수는 TableRoom 이 센다(스트림으로 온 쪽지를 받는 곳이라서다).
// 고른 탭도 TableRoom 이 쥔다. 쪽지 탭을 보고 있는지에 따라 수를 셀지가 갈린다.

import type { ReactNode } from 'react';

export type TalkTab = 'chat' | 'whisper' | 'dice';

type Props = {
  tab: TalkTab;
  onTab: (tab: TalkTab) => void;
  unreadWhispers: number;
  chat: ReactNode;
  whisper: ReactNode;
  dice: ReactNode;
};

const PANELS: Record<TalkTab, keyof Pick<Props, 'chat' | 'whisper' | 'dice'>> = { chat: 'chat', whisper: 'whisper', dice: 'dice' };

export function RoomTalk(props: Props) {
  const { tab, onTab, unreadWhispers } = props;
  return (
    <div className="room-talk">
      <div className="room-talk__tabs" role="tablist" aria-label="대화창">
        <TalkTabButton tab="chat" current={tab} onTab={onTab} label="채팅" />
        <TalkTabButton tab="whisper" current={tab} onTab={onTab} label="쪽지" count={unreadWhispers} />
        <TalkTabButton tab="dice" current={tab} onTab={onTab} label="주사위" />
      </div>
      <div id="room-talk-panel" role="tabpanel" aria-labelledby={`room-talk-tab-${tab}`}>
        {props[PANELS[tab]]}
      </div>
    </div>
  );
}

type TabProps = { tab: TalkTab; current: TalkTab; onTab: (tab: TalkTab) => void; label: string; count?: number };

function TalkTabButton({ tab, current, onTab, label, count = 0 }: TabProps) {
  return (
    <button
      type="button"
      role="tab"
      id={`room-talk-tab-${tab}`}
      className="room-talk__tab"
      aria-selected={current === tab}
      aria-controls="room-talk-panel"
      aria-label={unreadLabel(label, count)}
      onClick={() => onTab(tab)}
    >
      {label}
      {count > 0 ? (
        <span className="room-talk__count" aria-hidden="true">
          {count > 99 ? '99+' : count}
        </span>
      ) : null}
    </button>
  );
}

/** 탭의 읽히는 이름. "쪽지, 안 읽은 것 2개" */
export function unreadLabel(label: string, count: number): string {
  return count > 0 ? `${label}, 안 읽은 것 ${count}개` : label;
}
