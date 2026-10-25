// web/apps/web/src/pages/chat/conversation/ChatTranscriptButton.tsx
// 대화의 "기록 받기"(C3). 지금 보는 가지의 시작 상황, 말, 행동, 받아들인 변화, 이벤트 씬의 제목을 파일 하나로 받는다.
// 다른 가지와 메모는 들지 않는다. 형식과 파일 이름의 글은 TRPG 의 기록 받기와 같은 것을 쓴다(transcriptView).

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { CHAT_TRANSCRIPT_FORMATS, fetchConversationTranscript, type ChatTranscriptFormat } from '../../../api/chatConversation';
import { ApiError, NetworkError } from '../../../api/errors';
import { saveBlob } from '../../../components/saveFile';
import { fallbackFilename, formatHint, formatLabel } from '../../trpg/room/transcript/transcriptView';

type State = { busy: ChatTranscriptFormat | null; problem: string | null; saved: string | null };

export function ChatTranscriptButton({ conversationId, title }: { conversationId: string; title: string }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const downloading = useChatTranscript(conversationId, title);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        기록 받기
      </Button>
      <Dialog title="기록 받기" open={open} onClose={close}>
        <p className="hint">지금 보는 가지의 시작 상황, 말, 행동, 받아들인 변화를 파일 하나로 받습니다. 다른 가지와 기억 메모는 들지 않습니다. 10분에 10번까지 받습니다.</p>
        {downloading.problem ? <Notice tone="error">{downloading.problem}</Notice> : null}
        {downloading.saved ? <Notice>받았습니다: {downloading.saved}</Notice> : null}
        <ul className="plain-list transcript-formats" aria-label="기록의 형식">
          {CHAT_TRANSCRIPT_FORMATS.map((format) => (
            <li key={format}>
              <Button variant="secondary" busy={downloading.busy === format} disabled={downloading.busy !== null} onClick={() => void downloading.download(format)}>
                {formatLabel(format)}
              </Button>{' '}
              <span className="hint">{formatHint(format)}</span>
            </li>
          ))}
        </ul>
      </Dialog>
    </>
  );
}

/** 한 형식으로 받아 내려받게 한다. 한 번에 하나만(서버가 받는 수를 센다) */
function useChatTranscript(conversationId: string, title: string) {
  const [state, setState] = useState<State>({ busy: null, problem: null, saved: null });

  async function download(format: ChatTranscriptFormat): Promise<void> {
    if (state.busy) return;
    setState({ busy: format, problem: null, saved: null });
    try {
      const file = await fetchConversationTranscript(conversationId, format);
      const name = file.filename ?? fallbackFilename(title, format);
      saveBlob(file.blob, name);
      setState({ busy: null, problem: null, saved: name });
    } catch (error) {
      setState({ busy: null, problem: chatTranscriptProblem(error), saved: null });
    }
  }

  return { ...state, download };
}

/** 받지 못한 까닭 */
export function chatTranscriptProblem(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 받아 주세요.';
  if (error instanceof ApiError && error.status === 429) return `기록은 10분에 10번까지 받습니다. ${error.retryAfter ?? 60}초 뒤에 다시 받아 주세요.`;
  if (error instanceof ApiError && error.status === 404) return '볼 수 없는 대화라 기록을 받을 수 없습니다.';
  return '기록을 받지 못했습니다. 잠시 뒤에 다시 받아 주세요.';
}
