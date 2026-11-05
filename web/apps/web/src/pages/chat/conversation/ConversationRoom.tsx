// web/apps/web/src/pages/chat/conversation/ConversationRoom.tsx
// 대화(C3)의 화면(Stitch 21번). 위에 머리(대화 줄), 넓으면 왼쪽 열의 창 넷(ChatTools)과 오른쪽의 그림 창, 단추 줄, 대사창, 말 쓰기.
// 좁으면 머리, 그림, 대사창, 말 쓰기가 위아래고, 창 넷은 맨 아래 단추 줄(ChatDock)이 아래에서 올라오는 시트로 연다.
// 모델 고르기, 책갈피, 그림으로 저장은 겹쳐 연다.
// 한 대화에 한 생성이다. 이 화면이 받는 중이거나(turn) 다른 곳에서 쓰는 중이면(generating) 보내기, 다시 생성, 이어서, 대안, 행동, 고치기를 막는다.
// 답을 받는 일(말 보내기, 행동, 내 말 고치기)은 모델이 있어야 한다. 없으면 보내기 전에 고르게 한다(서버의 409 model_required 를 기다리지 않는다).
// 상대의 말 고치기는 모델을 부르지 않아 모델이 없어도 된다.
// 책갈피(#982)는 말마다 달고 떼며 받는 중에도 된다. 책갈피의 자리로 갈 때 지금 가지에 없는 말이면 가지를 바꾼다(바꾸는 것은 받는 중이 아닐 때만).
// 장면 그림(#983)은 답과 따로 돈다. 받는 중에도 지난 답을 그릴 수 있다. 시작하지 못한 까닭은 대사창 아래에 띄운다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import {
  chooseBranch,
  editAssistantMessage,
  openActionTurn,
  openContinueTurn,
  openEditTurn,
  openMessageTurn,
  openRegenerateTurn,
} from '../../../api/chatConversation';
import type { ConversationAction, ConversationDetail, ConversationMessage } from '../../../api/types';
import { bookmarkProblemText, isOnBranch, messageAnchor } from './bookmarksView';
import { snapshotProblemText } from './snapshotsView';
import { Composer } from './Composer';
import { ChatDock, useChatDock } from './ChatDock';
import { chatTools, ChatTools } from './ChatTools';
import { SheetClose } from '../../../components/SheetClose';
import { ConversationHeader } from './ConversationHeader';
import { conversationKey } from './conversationQueries';
import { pictureOf, tailSuggestions } from './conversationView';
import { MessageList } from './MessageList';
import { ModelDialog } from './ModelDialog';
import { PicturePane } from './PicturePane';
import { describeChangeProblem } from './turnProblem';
import { TurnNotice } from './TurnNotice';
import { useBookmarks } from './useBookmarks';
import { useConversationShortcuts } from './useConversationShortcuts';
import { useSnapshots } from './useSnapshots';
import type { TurnOpener, useConversationTurn } from './useConversationTurn';
import { WorldToolbar } from './WorldToolbar';
import { hasMap } from './worldView';
import { putQueryData } from '../../../queryClient';

type Props = { detail: ConversationDetail; turns: ReturnType<typeof useConversationTurn> };

export function ConversationRoom({ detail, turns }: Props) {
  const branching = useBranch(detail.id);
  const editing = useAssistantEdit(detail.id);
  const bookmarks = useBookmarks('chat', detail.id);
  const snapshots = useSnapshots('chat', detail.id);
  const [draft, setDraft] = useState('');
  const shortcuts = useConversationShortcuts('chat', detail.id, draft);
  const [choosingModel, setChoosingModel] = useState(false);
  const closeModel = useCallback(() => setChoosingModel(false), []);
  const tools = chatTools(hasMap(detail.character.document));
  const dock = useChatDock(tools[0] ?? null);
  const streaming = turns.turn !== null;
  const busy = streaming || detail.generating || branching.isPending || editing.isPending;
  const picture = pictureOf(detail, turns.turn ? { answering: turns.turn.userMessage, sprite: turns.turn.sprite } : null);

  /** 답을 받는다. 모델이 없으면 고르기를 열고 보내지 않는다. 서버가 받아들였으면 true */
  async function answer(open: TurnOpener): Promise<boolean> {
    if (detail.model?.usable !== true) {
      setChoosingModel(true);
      return false;
    }
    return turns.run(open);
  }

  async function send() {
    const content = draft;
    if (detail.model?.usable === true) setDraft('');
    const taken = await answer((signal) => openMessageTurn(detail.id, content, signal));
    if (!taken) setDraft((current) => current || content);
  }

  function act(action: ConversationAction) {
    void answer((signal) => openActionTurn(detail.id, action, signal));
  }

  /** 내 말은 새 가지로 고쳐 보내고, 상대의 말은 그 자리에서 고친다 */
  async function edit(message: ConversationMessage, content: string): Promise<boolean> {
    if (message.role === 'user') return answer((signal) => openEditTurn(detail.id, content, message.id, signal));
    try {
      await editing.mutateAsync({ messageId: message.id, content });
      return true;
    } catch {
      return false;
    }
  }

  function toggleBookmark(message: ConversationMessage) {
    const request = bookmarks.marked.has(message.id) ? { kind: 'remove' as const, messageId: message.id } : { kind: 'put' as const, messageId: message.id };
    bookmarks.change.mutate(request);
  }

  /** 책갈피의 자리로 간다. 지금 가지에 없으면 그 가지로 바꾼 뒤 내린다 */
  async function goTo(messageId: string) {
    if (!isOnBranch(detail.messages.map((message) => message.id), messageId)) {
      if (busy) return;
      try {
        await branching.mutateAsync(messageId);
      } catch {
        return;
      }
    }
    requestAnimationFrame(() => document.getElementById(messageAnchor(messageId))?.scrollIntoView?.({ block: 'center' }));
  }

  return (
    <main className="page conversation chat-room" data-sheet={dock.sheet ? 'tools' : undefined}>
      <ConversationHeader detail={detail} />
      <div className="chat-room__body">
        <div className="chat-room__main">
          <PicturePane picture={picture} name={detail.character.document.name} />
          <WorldToolbar detail={detail} busy={busy} onAction={act} bookmarks={bookmarks} onGoTo={(messageId) => void goTo(messageId)} />
          <MessageList
            detail={detail}
            turn={turns.turn}
            busy={busy}
            onBranch={(messageId) => branching.mutate(messageId)}
            onRegenerate={(messageId) => void answer((signal) => openRegenerateTurn(messageId, signal))}
            onContinue={(messageId) => void answer((signal) => openContinueTurn(messageId, signal))}
            onEdit={edit}
            marked={bookmarks.marked}
            onBookmark={toggleBookmark}
            snapshots={snapshots}
          />
          {detail.generating && !streaming ? <p className="hint">답을 쓰는 중입니다. 끝나면 보입니다.</p> : null}
          {branching.error ? <p className="ui-field__error">{describeChangeProblem(branching.error)}</p> : null}
          {editing.error ? <p className="ui-field__error">{describeChangeProblem(editing.error)}</p> : null}
          {bookmarks.change.error ? <p className="ui-field__error">{bookmarkProblemText(bookmarks.change.error)}</p> : null}
          {snapshots.draw.error ? <p className="ui-field__error">{snapshotProblemText(snapshots.draw.error)}</p> : null}
          <TurnNotice problem={turns.problem} failure={turns.failure} onChooseModel={() => setChoosingModel(true)} onClose={turns.clearNotice} />
          <Composer
            draft={draft}
            onDraft={setDraft}
            suggestions={tailSuggestions(detail.messages)}
            streaming={streaming}
            disabled={busy}
            canStop={Boolean(turns.turn?.generationId)}
            onSend={() => void send()}
            onStop={() => void turns.stop()}
            shortcuts={shortcuts}
          />
        </div>
        <div className="chat-room__tools">
          <SheetClose onClose={dock.closeSheet} />
          <ChatTools
            detail={detail}
            busy={busy}
            onAction={act}
            onChooseModel={() => setChoosingModel(true)}
            open={dock.open}
            onOpenChange={dock.setOpen}
          />
        </div>
      </div>
      <ChatDock tools={tools} dock={dock} />
      <ModelDialog detail={detail} open={choosingModel} onClose={closeModel} />
    </main>
  );
}

/** 다른 대안을 본다. 바뀐 대화를 그대로 받아 넣는다 */
function useBranch(conversationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chooseBranch(conversationId, messageId),
    onSuccess: (detail) => putQueryData(queryClient, conversationKey(conversationId), detail),
  });
}

/** 상대의 말을 고친다. 고친 말을 대화의 그 자리에 넣는다(대안은 그대로) */
function useAssistantEdit(conversationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, content }: { messageId: string; content: string }) => editAssistantMessage(messageId, content),
    onSuccess: (saved) =>
      putQueryData(queryClient, conversationKey(conversationId), (detail: ConversationDetail | undefined) =>
        detail ? { ...detail, messages: detail.messages.map((message) => (message.id === saved.id ? { ...message, ...saved } : message)) } : detail,
      ),
  });
}
