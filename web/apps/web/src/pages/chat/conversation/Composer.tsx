// web/apps/web/src/pages/chat/conversation/Composer.tsx
// 말 쓰기(C3). 다음 답 추천(누르면 입력칸을 채운다. 보내는 것은 사람이다), 입력칸, 보내기와 멈추기.
// Enter 로 보내고 Shift+Enter 로 줄을 바꾼다. 한글을 조합하는 중의 Enter 는 보내지 않는다.
// 답을 받는 중이면 멈추기만 누를 수 있다. 4000자까지, 빈칸만 있는 말은 보내지 않는다(서버의 규칙과 같다).

import { Button } from '@ai-trpg/ui';
import type { FormEvent, KeyboardEvent } from 'react';
import { TextAreaField } from '../../../components/TextAreaField';

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
};

export function Composer({ draft, onDraft, suggestions, streaming, disabled, canStop, onSend, onStop }: Props) {
  const sendable = canSend(draft) && !disabled;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (sendable) onSend();
  }

  function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
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
              <Button variant="secondary" disabled={disabled} onClick={() => onDraft(suggestion)}>
                {suggestion}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <TextAreaField label="보낼 말" rows={3} maxLength={MESSAGE_MAX} value={draft} onChange={(event) => onDraft(event.target.value)} onKeyDown={sendOnEnter} />
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
