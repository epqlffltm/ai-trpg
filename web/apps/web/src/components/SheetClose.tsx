// web/apps/web/src/components/SheetClose.tsx
// 좁은 화면의 플레이 화면(테이블 방, chat 대화)에서 아래에서 올라오는 시트 맨 위의 닫기. 넓은 화면에서는 CSS 가 숨긴다(room-sheet__head).

export function SheetClose({ onClose }: { onClose: () => void }) {
  return (
    <div className="room-sheet__head">
      <button type="button" className="room-sheet__close" onClick={onClose}>
        시트 닫기
      </button>
    </div>
  );
}
