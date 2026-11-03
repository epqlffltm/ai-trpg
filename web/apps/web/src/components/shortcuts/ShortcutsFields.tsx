// web/apps/web/src/components/shortcuts/ShortcutsFields.tsx
// 단축어 목록의 칸들(#981). 더하기, 지우기, 앞으로 옮기기. 저장(폼)은 쓰는 쪽이 맡는다.
// 캐릭터와 세계관의 단축어 탭, 내 단축어 화면이 함께 쓴다. 규칙은 shortcutsForm.ts 다.

import { Button, TextField } from '@ai-trpg/ui';
import { TextAreaField } from '../TextAreaField';
import {
  addShortcut,
  changeShortcut,
  moveShortcutUp,
  removeShortcut,
  SHORTCUT_BODY_MAX,
  SHORTCUT_DESCRIPTION_MAX,
  SHORTCUT_NAME_MAX,
  SHORTCUTS_MAX,
  type ShortcutDraft,
} from './shortcutsForm';

type Props = {
  shortcuts: ShortcutDraft[];
  hints: Record<number, Record<string, string>>;
  onChange: (update: (current: ShortcutDraft[]) => ShortcutDraft[]) => void;
};

export function ShortcutsFields({ shortcuts, hints, onChange }: Props) {
  return (
    <>
      {shortcuts.length === 0 ? <p>아직 단축어가 없습니다.</p> : null}
      <ol className="plain-list" aria-label="단축어">
        {shortcuts.map((shortcut, index) => (
          // 단축어에는 서버의 id 가 없다. 차례가 곧 그 단축어다
          <li key={index} className="scenario-opening">
            <TextField
              label={`단축어 ${index + 1}의 이름`}
              maxLength={SHORTCUT_NAME_MAX}
              value={shortcut.name}
              onChange={(event) => onChange((current) => changeShortcut(current, index, { name: event.target.value }))}
              error={hints[index]?.name}
            />
            <TextField
              label={`단축어 ${index + 1}의 설명`}
              maxLength={SHORTCUT_DESCRIPTION_MAX}
              value={shortcut.description}
              onChange={(event) => onChange((current) => changeShortcut(current, index, { description: event.target.value }))}
              error={hints[index]?.description}
            />
            <TextAreaField
              label={`단축어 ${index + 1}의 본문`}
              rows={4}
              maxLength={SHORTCUT_BODY_MAX}
              value={shortcut.body}
              onChange={(event) => onChange((current) => changeShortcut(current, index, { body: event.target.value }))}
              error={hints[index]?.body}
              hint={`${shortcut.body.length} / ${SHORTCUT_BODY_MAX}자. 부른 턴에만 내 말 끝에 붙어 모델에 갑니다.`}
            />
            <div className="form-actions">
              {index > 0 ? (
                <Button variant="quiet" onClick={() => onChange((current) => moveShortcutUp(current, index))} aria-label={`단축어 ${index + 1} 앞으로`}>
                  앞으로
                </Button>
              ) : null}
              <Button variant="quiet" onClick={() => onChange((current) => removeShortcut(current, index))} aria-label={`단축어 ${index + 1} 지우기`}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={shortcuts.length >= SHORTCUTS_MAX} onClick={() => onChange(addShortcut)}>
          단축어 더하기
        </Button>{' '}
        <span className="hint">
          {shortcuts.length} / {SHORTCUTS_MAX}
        </span>
      </p>
    </>
  );
}
