// web/apps/web/src/pages/chat/studio/characters/spritesForm.ts
// 캐릭터 그림 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/characters/schemas.py 의 Sprite).
//
//   - 캐릭터 그림은 배경이 투명한 서 있는 그림이다. 대화의 그림 창에서 배경 위에 겹친다. 30 개까지
//   - 표정(20자)은 이름이다. 빈 글이면 기본 표정이다
//   - 차림은 옷(물건 탭의 종류가 옷인 것)의 id 다. 비우면 처음 차림이다. 사용자가 그 옷을 건네 상대가 입으면 그 차림의 그림을 쓴다
//   - 같은 표정(대소문자를 가리지 않는다)과 차림의 그림은 하나다
//   - id 는 화면이 붙인다(keys.ts). 그림은 꼭 있어야 한다

import type { AssetCharacterDetail, AssetCharacterUpdate } from '../../../../api/types';

export const SPRITES_MAX = 30;
export const EXPRESSION_MAX = 20;

/** 차림은 빈 글이면 처음 차림이다. 그림은 아직 올리지 않았으면 null */
export type SpriteDraft = { id: string; imageId: string | null; expression: string; outfit: string };

export function spriteDrafts(character: AssetCharacterDetail): SpriteDraft[] {
  return character.sprites.map((sprite) => ({
    id: sprite.id,
    imageId: sprite.image_id,
    expression: sprite.expression ?? '',
    outfit: sprite.outfit ?? '',
  }));
}

export function addSprite(sprites: SpriteDraft[], id: string): SpriteDraft[] {
  return sprites.length < SPRITES_MAX ? [...sprites, { id, imageId: null, expression: '', outfit: '' }] : sprites;
}

export function changeSprite(sprites: SpriteDraft[], id: string, changes: Partial<Omit<SpriteDraft, 'id'>>): SpriteDraft[] {
  return sprites.map((sprite) => (sprite.id === id ? { ...sprite, ...changes } : sprite));
}

export function removeSprite(sprites: SpriteDraft[], id: string): SpriteDraft[] {
  return sprites.filter((sprite) => sprite.id !== id);
}

function pairOf(sprite: SpriteDraft): string {
  return `${sprite.expression.trim().toLocaleLowerCase()}\u0000${sprite.outfit}`;
}

/** 그림마다(id → 글)의 문제 */
export function spritesHints(sprites: SpriteDraft[]): Record<string, string> {
  const hints: Record<string, string> = {};
  const seen = new Set<string>();
  for (const sprite of sprites) {
    const pair = pairOf(sprite);
    if (sprite.imageId === null) hints[sprite.id] = '그림을 올려 주세요.';
    else if (sprite.expression.trim().length > EXPRESSION_MAX) hints[sprite.id] = `표정은 ${EXPRESSION_MAX}자까지입니다.`;
    else if (seen.has(pair)) hints[sprite.id] = '같은 표정과 차림의 그림이 이미 있습니다.';
    seen.add(pair);
  }
  return hints;
}

/** 캐릭터 그림 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toSpritesBody(sprites: SpriteDraft[]): AssetCharacterUpdate {
  return {
    sprites: sprites.map((sprite) => ({
      id: sprite.id,
      image_id: sprite.imageId as string,
      expression: sprite.expression.trim(),
      outfit: sprite.outfit === '' ? null : sprite.outfit,
    })),
  };
}
