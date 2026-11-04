// web/apps/web/src/pages/chat/conversation/Composer.tsx
// 말 쓰기(C3). 다음 답 추천(누르면 입력칸을 채운다. 보내는 것은 사람이다), 입력칸, 보내기와 멈추기.
// Enter 로 보내고 Shift+Enter 로 줄을 바꾼다. 한글을 조합하는 중의 Enter 는 보내지 않는다.
// 답을 받는 중이면 멈추기만 누를 수 있다. 4000자까지, 빈칸만 있는 말은 보내지 않는다(서버의 규칙과 같다).
// "/"로 시작해 이름을 적는 중이면 고를 수 있는 단축어를 보인다(#981, shortcutPicks.ts). 고르면 "/이름 "이 되고 입력칸으로 돌아간다.
// 목록이 보이는 동안 입력칸의 위아래 화살표는 고를 것을 옮기고, Enter 는 보내지 않고 고르며, Esc 는 목록을 닫는다(글을 고치면 다시 보인다).

import { Button } from '@ai-trpg/ui';
import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { ConversationShortcut } from '../../../api/conversationShortcuts';
import { TextAreaField } from '../../../components/TextAreaField';
import { movedPick, pickedDraft, pickLabel, picksFor } from './shortcutPicks';

export const MESSAGE_MAX = 4000;

type Props = {
  draft: string;
  onDraft: (value: string) => void;
  suggestions: string[];
  /** 답을 받는 중이다(이 화면이). 멈추기를 보인다 */
  streaming: boolean;
  /** 보낼 수 없다(받는 중, 다른 곳에서 쓰는 중, 모델 없음 …) */
  disabled: boolean;
  canStop: boolean;
  onSend: () => void;
  onStop: () => void;
  /** 고를 수 있는 단축어(#981). 없으면 고르는 목록을 보이지 않는다 */
  shortcuts?: readonly ConversationShortcut[];
};

export function Composer({ draft, onDraft, suggestions, streaming, disabled, canStop, onSend, onStop, shortcuts = [] }: Props) {
  const sendable = canSend(draft) && !disabled;
  const input = useRef<HTMLTextAreaElement>(null);
  const [active, setActive] = useState(0);
  // Esc 로 닫은 때의 글. 글이 바뀌면 다시 보인다
  const [closedAt, setClosedAt] = useState<string | null>(null);
  const picks = closedAt === draft ? [] : picksFor(draft, shortcuts);
  const current = Math.min(active, Math.max(picks.length - 1, 0));

  function write(value: string) {
    setActive(0);
    onDraft(value);
  }

  function pick(shortcut: ConversationShortcut) {
    write(pickedDraft(shortcut));
    input.current?.focus();
  }

  /** 목록이 보이는 동안의 키. 쓴 키면 true */
  function choosePickByKey(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
    if (picks.length === 0 || event.nativeEvent.isComposing) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') setActive(movedPick(current, picks.length, event.key === 'ArrowDown' ? 1 : -1));
    else if (event.key === 'Enter' && !event.shiftKey) pick(picks[current] as ConversationShortcut);
    else if (event.key === 'Escape') setClosedAt(draft);
    else return false;
    event.preventDefault();
    return true;
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (sendable) onSend();
  }

  function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (choosePickByKey(event)) return;
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (sendable) onSend();
  }

  return (
    <form className="conversation__composer" onSubmit={submit}>
      {suggestions.length > 0 && !streaming ? (
        <ul className="plain-list chat-suggestions" aria-label="다음 답 추천">
          {suggestions.map((suggestion) => (
            <li key={suggestion}>
              <Button variant="secondary" disabled={disabled} onClick={() => write(suggestion)}>
                {suggestion}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {picks.length > 0 ? (
        <ul className="plain-list chat-suggestions" aria-label="단축어">
          {picks.map((shortcut, index) => (
            <li key={shortcut.name}>
              <Button variant="quiet" aria-current={index === current ? 'true' : undefined} onClick={() => pick(shortcut)}>
                {pickLabel(shortcut)}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <TextAreaField ref={input} label="보낼 말" rows={3} maxLength={MESSAGE_MAX} value={draft} onChange={(event) => write(event.target.value)} onKeyDown={sendOnEnter} />
      <div className="conversation__send">
        {streaming ? (
          <Button variant="secondary" disabled={!canStop} onClick={onStop}>
            멈추기
          </Button>
        ) : null}
        <Button type="submit" disabled={!sendable}>
          보내기
        </Button>
      </div>
    </form>
  );
}

/** 보낼 수 있는 말인가. 빈칸이 아닌 글자가 있고 4000자까지 */
export function canSend(text: string): boolean {
  return /\S/.test(text) && text.length <= MESSAGE_MAX;
}
