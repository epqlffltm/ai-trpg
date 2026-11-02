// web/apps/web/src/pages/chat/conversation/BookmarkToggle.tsx
// 말 아래의 "책갈피" 단추(#982). 누르면 달고, 단 말이면 뗀다. 답을 받는 중에도 된다(모델을 부르지 않는다).
// chat 의 말과 story 의 말이 함께 쓴다.

import { Button } from '@ai-trpg/ui';

type Props = { marked: boolean; disabled: boolean; onToggle: () => void };

export function BookmarkToggle({ marked, disabled, onToggle }: Props) {
  return (
    <Button variant="quiet" aria-pressed={marked} disabled={disabled} onClick={onToggle}>
      {marked ? '책갈피 떼기' : '책갈피'}
    </Button>
  );
}
