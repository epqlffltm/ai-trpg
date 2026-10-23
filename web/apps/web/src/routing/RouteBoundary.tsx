// web/apps/web/src/routing/RouteBoundary.tsx
// 경로의 화면이 그리다 깨졌을 때 머리(AppHeader)는 남기고 화면 자리에만 안내를 보인다. 없으면 빈 화면이 된다.
//
//   - 조각을 받지 못했으면(새로 올린 뒤의 예전 탭) 새 버전이 나왔을 수 있다고 알리고 새로 고치기 단추를 둔다.
//     저절로 새로 고치지 않는다. 쓰던 선언이나 채팅의 글이 날아갈 수 있다(2026-10-23 에 정함)
//   - 그 밖의 오류는 화면을 그리지 못했다고만 알린다. 같은 단추를 둔다
//   - 다른 경로로 가면(resetKey 가 바뀌면) 안내를 거두고 다시 그린다. 경로마다 key 로 새로 만들지 않는다(같은 화면의 상태를 지킨다)

import { Button, Notice } from '@ai-trpg/ui';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { isChunkLoadError } from './chunkError';

type Props = { resetKey: string; children: ReactNode; onReload?: () => void };
// at: 오류가 난 경로. 그 경로에 있는 동안만 안내를 보인다
type State = { error: unknown; at: string | null };

const EMPTY: State = { error: null, at: null };

export class RouteBoundary extends Component<Props, State> {
  state: State = EMPTY;

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error };
  }

  /** 오류가 난 경로를 적고, 다른 경로로 오면 거둔다 */
  static getDerivedStateFromProps(props: Props, state: State): State | null {
    if (state.error === null) return null;
    if (state.at === null) return { ...state, at: props.resetKey };
    return state.at === props.resetKey ? null : EMPTY;
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('화면을 그리지 못했다', error, info.componentStack);
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return <RouteFailure chunk={isChunkLoadError(this.state.error)} onReload={this.props.onReload ?? reloadPage} />;
  }
}

function reloadPage() {
  window.location.reload();
}

function RouteFailure({ chunk, onReload }: { chunk: boolean; onReload: () => void }) {
  return (
    <div className="page">
      <Notice tone="error">
        {chunk ? '화면을 불러오지 못했습니다. 새 버전이 나왔을 수 있습니다. 새로 고쳐 주세요.' : '화면을 그리지 못했습니다. 새로 고쳐 보세요.'}
      </Notice>
      <div className="actions">
        <Button onClick={onReload}>새로 고치기</Button>
      </div>
    </div>
  );
}
