// web/apps/web/src/pages/chat/studio/characters/StartsTab.tsx
// 캐릭터의 시작 상황 탭(C6). 대화를 여는 사람이 하나를 고른다. 제목은 고르는 목록에, 상황은 모델에 간다.
// 더하기, 지우기, 앞으로 옮기기. 게시하려면 하나는 있어야 한다. 처음 있는 장소는 지도 탭, 시작 소지품은 물건 탭에서 정한다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import {
  addStart,
  changeStart,
  moveStartUp,
  removeStart,
  SITUATION_MAX,
  START_TITLE_MAX,
  startDrafts,
  STARTS_MAX,
  startsHints,
  toStartsBody,
  type StartDraft,
} from './startsForm';
import { useCharacterSave } from './useCharacterSave';

export function StartsTab({ character }: { character: AssetCharacterDetail }) {
  const [starts, setStarts] = useState<StartDraft[]>(() => startDrafts(character.starts));
  const saving = useCharacterSave(character.id);
  const hints = startsHints(starts);

  async function submit() {
    const saved = await saving.save(toStartsBody(starts));
    if (saved) setStarts(startDrafts(saved.starts));
  }

  function change(index: number, changes: Partial<StartDraft>) {
    setStarts((current) => changeStart(current, index, changes));
  }

  return (
    <CharacterForm
      label="시작 상황"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">대화를 여는 사람이 하나를 고릅니다. 맨 앞의 것이 기본입니다. 게시하려면 하나는 있어야 합니다.</p>
      {starts.length === 0 ? <p>아직 시작 상황이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="시작 상황">
        {starts.map((start, index) => (
          // 시작 상황에는 서버의 id 가 없다. 차례가 곧 그 시작 상황이다
          <li key={index} className="scenario-opening">
            <TextField
              label={`시작 상황 ${index + 1}의 제목`}
              maxLength={START_TITLE_MAX}
              value={start.title}
              onChange={(event) => change(index, { title: event.target.value })}
              error={hints[index]?.title}
            />
            <TextAreaField
              label={`시작 상황 ${index + 1}의 상황`}
              rows={5}
              maxLength={SITUATION_MAX}
              value={start.situation}
              onChange={(event) => change(index, { situation: event.target.value })}
              error={hints[index]?.situation}
              hint={`${start.situation.length} / ${SITUATION_MAX}자. 모델이 읽는 첫 장면입니다.`}
            />
            <TextField
              label={`시작 상황 ${index + 1}의 시각(시, 0~23)`}
              inputMode="numeric"
              value={start.hour}
              onChange={(event) => change(index, { hour: event.target.value })}
              error={hints[index]?.hour}
            />
            <div className="form-actions">
              {index > 0 ? (
                <Button variant="quiet" onClick={() => setStarts((current) => moveStartUp(current, index))} aria-label={`시작 상황 ${index + 1} 앞으로`}>
                  앞으로
                </Button>
              ) : null}
              <Button variant="quiet" onClick={() => setStarts((current) => removeStart(current, index))} aria-label={`시작 상황 ${index + 1} 지우기`}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={starts.length >= STARTS_MAX} onClick={() => setStarts(addStart)}>
          시작 상황 더하기
        </Button>{' '}
        <span className="hint">
          {starts.length} / {STARTS_MAX}
        </span>
      </p>
    </CharacterForm>
  );
}
