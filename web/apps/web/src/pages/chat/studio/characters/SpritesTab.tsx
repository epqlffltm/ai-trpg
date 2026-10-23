// web/apps/web/src/pages/chat/studio/characters/SpritesTab.tsx
// 캐릭터 그림 탭(C6): 표정과 차림마다의 서 있는 그림. 배경이 투명해야 대화의 그림 창에서 배경 위에 자연스럽게 겹친다.
// 투명한지는 서버가 보지 않으므로 미리 보기를 체크무늬 위에 그려 보인다. 차림은 물건 탭에서 저장한 옷에서 고른다.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail } from '../../../../api/types';
import { ImagePicker } from '../../../../components/ImagePicker';
import { CharacterForm } from './CharacterForm';
import { newKey } from './keys';
import {
  addSprite,
  changeSprite,
  EXPRESSION_MAX,
  removeSprite,
  spriteDrafts,
  SPRITES_MAX,
  spritesHints,
  toSpritesBody,
  type SpriteDraft,
} from './spritesForm';
import { useCharacterSave } from './useCharacterSave';

export function SpritesTab({ character }: { character: AssetCharacterDetail }) {
  const [sprites, setSprites] = useState<SpriteDraft[]>(() => spriteDrafts(character));
  const saving = useCharacterSave(character.id);
  const hints = spritesHints(sprites);
  const clothes = character.items.filter((item) => item.kind === 'clothing');

  async function submit() {
    const saved = await saving.save(toSpritesBody(sprites));
    if (saved) setSprites(spriteDrafts(saved));
  }

  function change(id: string, changes: Partial<Omit<SpriteDraft, 'id'>>) {
    setSprites((current) => changeSprite(current, id, changes));
  }

  return (
    <CharacterForm
      label="캐릭터 그림"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">
        배경이 투명한 서 있는 그림입니다. 표정과 차림마다 하나씩 둡니다. 표정을 비우면 기본 표정, 차림을 비우면 처음 차림입니다. 사용자가 옷을 건네 상대가 입으면 그 차림의 그림을
        씁니다.
      </p>
      {sprites.length === 0 ? <p>아직 캐릭터 그림이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="캐릭터 그림">
        {sprites.map((sprite, index) => (
          <li key={sprite.id} className="scenario-opening">
            <ImagePicker label={`캐릭터 그림 ${index + 1}`} imageId={sprite.imageId} onChange={(imageId) => change(sprite.id, { imageId })} checkered />
            <TextField
              label={`캐릭터 그림 ${index + 1}의 표정(선택)`}
              maxLength={EXPRESSION_MAX}
              value={sprite.expression}
              onChange={(event) => change(sprite.id, { expression: event.target.value })}
              error={hints[sprite.id]}
            />
            <SelectField label={`캐릭터 그림 ${index + 1}의 차림`} value={sprite.outfit} onChange={(event) => change(sprite.id, { outfit: event.target.value })}>
              <option value="">처음 차림</option>
              {clothes.map((item, at) => (
                <option key={item.id} value={item.id}>
                  {item.name || `옷 ${at + 1}`}
                </option>
              ))}
            </SelectField>
            <div className="form-actions">
              <Button variant="quiet" aria-label={`캐릭터 그림 ${index + 1} 지우기`} onClick={() => setSprites((current) => removeSprite(current, sprite.id))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={sprites.length >= SPRITES_MAX}
          onClick={() => setSprites((current) => addSprite(current, newKey('sprite', current.map((sprite) => sprite.id))))}
        >
          캐릭터 그림 더하기
        </Button>{' '}
        <span className="hint">
          {sprites.length} / {SPRITES_MAX}
        </span>
      </p>
    </CharacterForm>
  );
}
