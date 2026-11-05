// web/apps/web/src/pages/story/StoryRoom.tsx
// 장면(D2)의 화면(Stitch 22번). 위에 머리(세계관, 날짜·시간대·장소, 모델). 넓으면 오른쪽에 그림 창, 장면의 인물, 대사창, 말 쓰기,
// 왼쪽 열에 창(StoryTools: 지도·이동, 소지품·건네기, 인물, 기록, 기억, 페르소나·모델)과 그 아래 행동 줄(StoryActionBar). chat 대화와 같은 배치(chat-room)다.
// 좁으면 오른쪽의 것이 위아래고, 왼쪽 열은 맨 아래 단추 줄(ToolDock)이 아래에서 올라오는 시트로 연다.
// 한 세션에 한 생성이다. 받는 중이면 보내기, 다시 생성, 대안, 모델 바꾸기를 막는다. 모델이 없으면 보내기 전에 고르게 한다.
// 끝난 세션(엔딩을 봤고 후일담이 없다)은 말 쓰기와 행동을 숨긴다. 가지와 다시 생성(엔딩 장면을 다시 쓰기)은 된다.
// 행동(시간 보내기, 하루 마치기, 이동, 선택지, 건네기, 고백)은 엔진이 판정하고 반응을 받는다. 말과 같이 모델이 있어야 한다.
// 엔딩 장면의 답이 끝나면 엔딩 화면을 띄운다. 위의 그림 창은 장면의 일러스트나 지금 장소·시간대의 배경이다.
// 내 말 고치기는 새 가지로 답을 다시 받고(모델이 있어야 한다), 답 고치기는 조각마다 글만 그 자리에서 고친다(청구 없음). 끊긴 답은 이어 쓴다.
// 책갈피(#982)는 말마다 달고 떼며 받는 중에도 된다. 책갈피의 자리로 갈 때 지금 가지에 없는 말이면 가지를 바꾼다.
// 그림으로 저장(#982)은 지금 가지의 말들로 이 기기에서 그림을 만든다.
// 장면 그림(#983)은 답과 따로 돈다. 받는 중에도 지난 답을 그릴 수 있다. 시작하지 못한 까닭은 대사창 아래에 띄운다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import {
  chooseStoryBranch,
  editStoryAnswer,
  openStoryActionTurn,
  openStoryContinueTurn,
  openStoryMessageTurn,
  openStoryRegenerateTurn,
  type StoryAction,
  type StoryMessage,
  type StorySession,
} from '../../api/story';
import { bookmarkProblemText, isOnBranch, messageAnchor } from '../chat/conversation/bookmarksView';
import { snapshotProblemText } from '../chat/conversation/snapshotsView';
import { Composer } from '../chat/conversation/Composer';
import { describeChangeProblem } from '../chat/conversation/turnProblem';
import { TurnNotice } from '../chat/conversation/TurnNotice';
import { useBookmarks } from '../chat/conversation/useBookmarks';
import { useSnapshots } from '../chat/conversation/useSnapshots';
import { useConversationShortcuts } from '../chat/conversation/useConversationShortcuts';
import { freshEnding, pendingChoices } from './storyActions';
import { StoryActionBar } from './StoryActionBar';
import { storyHasMap, storyToolLabel, storyTools, StoryTools } from './StoryTools';
import { SheetClose } from '../../components/SheetClose';
import { ToolDock, useToolDock } from '../../components/ToolDock';
import { StoryBookmarksButton } from './StoryBookmarksButton';
import { StoryScreenshotButton } from './StoryScreenshotButton';
import { backgroundOf, expressionsOf, sceneOf as pictureSceneOf } from './storyCastView';
import { StoryCastRow } from './StoryCastRow';
import { StoryChoices } from './StoryChoices';
import { StoryEnding } from './StoryEnding';
import { StoryHeader } from './StoryHeader';
import { StoryMessageList } from './StoryMessageList';
import { StoryModelDialog } from './StoryModelDialog';
import { StoryPicture } from './StoryPicture';
import { storySessionKey } from './storyQueries';
import { describeStartProblem, describeStoryEditProblem } from './storyTurnProblem';
import { sceneOf, sceneSegments, storySuggestions, visibleStoryMessages } from './storyView';
import { isEnded, placeName } from './storyWorld';
import { useStartStorySession } from './useStartStorySession';
import type { StoryTurnOpener, useStoryTurn } from './useStoryTurn';
import { putQueryData } from '../../queryClient';

type Props = { session: StorySession; turns: ReturnType<typeof useStoryTurn> };

export function StoryRoom({ session, turns }: Props) {
  const branching = useBranch(session.id);
  const editing = useAnswerEdit(session.id);
  const bookmarks = useBookmarks('story', session.id);
  const snapshots = useSnapshots('story', session.id);
  const [draft, setDraft] = useState('');
  const shortcuts = useConversationShortcuts('story', session.id, draft);
  const [choosingModel, setChoosingModel] = useState(false);
  const closeModel = useCallback(() => setChoosingModel(false), []);
  const streaming = turns.turn !== null;
  const busy = streaming || branching.isPending || editing.isPending;
  const scene = sceneOf(session.state, turns.turn);
  const expressions = expressionsOf(sceneSegments(visibleStoryMessages(session.messages, turns.turn)));
  const view = session.view;
  const ended = isEnded(view, scene.state);
  const restarting = useStartStorySession();
  const [closedEnding, setClosedEnding] = useState<string | null>(null);
  const ending = streaming ? null : freshEnding(session.messages);
  const showEnding = ending !== null && ending.messageId !== closedEnding;
  const choices = streaming || ended ? null : pendingChoices(view, scene.state.choosing);
  const tools = storyTools(storyHasMap(view, scene.state, ended));
  const dock = useToolDock(tools[0] ?? null);

  /** 답을 받는다. 모델이 없으면 고르기를 열고 보내지 않는다. 서버가 받아들였으면 true */
  async function answer(open: StoryTurnOpener): Promise<boolean> {
    if (session.model?.usable !== true) {
      setChoosingModel(true);
      return false;
    }
    return turns.run(open);
  }

  async function send() {
    const content = draft;
    if (session.model?.usable === true) setDraft('');
    const taken = await answer((signal) => openStoryMessageTurn(session.id, content, signal));
    if (!taken) setDraft((current) => current || content);
  }

  /** 내 말을 고쳐 새 가지로 보낸다(답을 다시 받는다, 청구) */
  function sendEdit(message: StoryMessage, content: string): Promise<boolean> {
    return answer((signal) => openStoryMessageTurn(session.id, content, signal, message.id));
  }

  /** 답의 조각을 그 자리에서 고친다(청구 없음) */
  async function saveSegments(message: StoryMessage, segments: string[]): Promise<boolean> {
    try {
      await editing.mutateAsync({ messageId: message.id, segments });
      return true;
    } catch {
      return false;
    }
  }

  function act(action: StoryAction): Promise<boolean> {
    return answer((signal) => openStoryActionTurn(session.id, action, signal));
  }

  function toggleBookmark(message: StoryMessage) {
    const request = bookmarks.marked.has(message.id) ? { kind: 'remove' as const, messageId: message.id } : { kind: 'put' as const, messageId: message.id };
    bookmarks.change.mutate(request);
  }

  /** 책갈피의 자리로 간다. 지금 가지에 없으면 그 가지로 바꾼 뒤 내린다 */
  async function goTo(messageId: string) {
    if (!isOnBranch(session.messages.map((message) => message.id), messageId)) {
      if (busy) return;
      try {
        await branching.mutateAsync(messageId);
      } catch {
        return;
      }
    }
    requestAnimationFrame(() => document.getElementById(messageAnchor(messageId))?.scrollIntoView?.({ block: 'center' }));
  }

  const sessionTools = (
    <>
      <StoryBookmarksButton source={bookmarks} busy={busy} onGoTo={(messageId) => void goTo(messageId)} />
      <StoryScreenshotButton session={session} />
    </>
  );

  return (
    <main className="page conversation story chat-room" data-sheet={dock.sheet ? 'tools' : undefined}>
      <StoryHeader session={session} state={scene.state} />
      <div className="chat-room__body">
        <div className="chat-room__main">
          <StoryPicture
            scene={pictureSceneOf(view, session.messages, turns.turn?.userMessage ?? null)}
            background={backgroundOf(view, scene.state)}
            placeName={placeName(view, scene.state.place)}
          />
          <StoryCastRow view={view} state={scene.state} cast={scene.cast} expressions={expressions} disabled={busy || ended} onAct={act} />
          <StoryMessageList
            session={session}
            turn={turns.turn}
            busy={busy}
            onBranch={(messageId) => branching.mutate(messageId)}
            onRegenerate={(messageId) => void answer((signal) => openStoryRegenerateTurn(messageId, signal))}
            onContinue={(messageId) => void answer((signal) => openStoryContinueTurn(messageId, signal))}
            onSendEdit={sendEdit}
            onSaveSegments={saveSegments}
            marked={bookmarks.marked}
            onBookmark={toggleBookmark}
            snapshots={snapshots}
          />
          {branching.error ? <p className="ui-field__error">{describeChangeProblem(branching.error)}</p> : null}
          {editing.error ? <p className="ui-field__error">{describeStoryEditProblem(editing.error)}</p> : null}
          {bookmarks.change.error ? <p className="ui-field__error">{bookmarkProblemText(bookmarks.change.error)}</p> : null}
          {snapshots.draw.error ? <p className="ui-field__error">{snapshotProblemText(snapshots.draw.error)}</p> : null}
          {showEnding ? (
            <StoryEnding
              worldId={session.world.id}
              view={view}
              endingId={ending.endingId}
              starting={restarting.isPending}
              onRestart={() => restarting.mutate({ worldId: session.world.id })}
              onClose={() => setClosedEnding(ending.messageId)}
            />
          ) : null}
          {restarting.error ? <p className="ui-field__error">{describeStartProblem(restarting.error)}</p> : null}
          {choices ? <StoryChoices pending={choices} disabled={busy} onAct={act} /> : null}
          <TurnNotice problem={turns.problem} failure={turns.failure} onChooseModel={() => setChoosingModel(true)} onClose={turns.clearNotice} />
          {ended ? (
            <div className="story-actions">
              <p className="hint story-ended">이야기가 끝났습니다. 대안을 넘겨 보거나 끝의 장면을 다시 쓸 수 있습니다.</p>
              {sessionTools}
            </div>
          ) : null}
          {ended ? null : (
            <Composer
              draft={draft}
              onDraft={setDraft}
              suggestions={storySuggestions(session.messages, choices !== null)}
              streaming={streaming}
              disabled={busy}
              canStop={Boolean(turns.turn?.generationId)}
              onSend={() => void send()}
              onStop={() => void turns.stop()}
              shortcuts={shortcuts}
            />
          )}
        </div>
        <div className="chat-room__tools">
          <SheetClose onClose={dock.closeSheet} />
          <StoryTools
            session={session}
            state={scene.state}
            tools={tools}
            disabled={busy}
            onAct={act}
            onChooseModel={() => setChoosingModel(true)}
            open={dock.open}
            onOpenChange={dock.setOpen}
          />
          {ended ? null : <StoryActionBar view={view} state={scene.state} disabled={busy} onAct={act} tools={sessionTools} />}
        </div>
      </div>
      <ToolDock label="장면의 단추 줄" tools={tools.map((tool) => ({ id: tool, label: storyToolLabel(tool) }))} dock={dock} />
      <StoryModelDialog session={session} open={choosingModel} onClose={closeModel} />
    </main>
  );
}

/** 다른 대안을 본다. 바뀐 세션을 그대로 받아 넣는다 */
function useBranch(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chooseStoryBranch(sessionId, messageId),
    onSuccess: (session) => putQueryData(queryClient, storySessionKey(sessionId), session),
  });
}


/** 답을 조각마다 고친다. 고친 말을 세션의 그 자리에 넣는다(대안은 그대로). 조각의 수가 어긋났으면 다시 읽는다 */
function useAnswerEdit(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, segments }: { messageId: string; segments: string[] }) => editStoryAnswer(messageId, segments),
    onSuccess: (saved) =>
      putQueryData(queryClient, storySessionKey(sessionId), (session: StorySession | undefined) =>
        session ? { ...session, messages: session.messages.map((message) => (message.id === saved.id ? { ...message, ...saved } : message)) } : session,
      ),
    onError: () => queryClient.invalidateQueries({ queryKey: storySessionKey(sessionId) }),
  });
}
