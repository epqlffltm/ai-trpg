// web/apps/web/src/pages/trpg/room/status/ActionButton.tsx
// 패널에서 선언으로 가는 작은 단추("쓰기", "건네기", "가기" …). 누르면 선언 입력의 행동 칸을 채워 달라고 부탁한다.
// 보내는 것은 선언 입력이다. 선언을 받는 중이 아니거나 내 캐릭터가 행동할 수 없으면 막는다.

import type { ActionDraft } from '../round/action/actionDraft';

/** 패널이 선언으로 가는 길. 진행 중이 아니면(끝난 테이블) null 이라 단추를 보이지 않는다 */
export type ActionShortcuts = { enabled: boolean; request: (patch: Partial<ActionDraft>) => void } | null;

type Props = { shortcuts: ActionShortcuts; patch: Partial<ActionDraft>; label: string; what: string };

export function ActionButton({ shortcuts, patch, label, what }: Props) {
  if (!shortcuts) return null;
  return (
    <button
      type="button"
      className="action-chip"
      disabled={!shortcuts.enabled}
      aria-label={`${what} ${label}`}
      onClick={() => shortcuts.request(patch)}
    >
      {label}
    </button>
  );
}
