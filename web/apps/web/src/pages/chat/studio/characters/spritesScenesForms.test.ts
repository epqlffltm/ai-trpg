// web/apps/web/src/pages/chat/studio/characters/spritesScenesForms.test.ts
// 캐릭터 그림과 이벤트 씬 탭(C6)의 입력: 그림이 꼭 있어야 하기, 같은 표정과 차림, 처음 차림은 null,
// 조건의 종류를 바꾸면 대상을 비우기, 대상의 목록(장소, 물건, 호감도 단계), 보낼 때의 모양.

import { describe, expect, it } from 'vitest';
import type { AssetCharacterDetail } from '../../../../api/types';
import { addScene, changeScene, sceneDrafts, SCENES_MAX, scenesHints, sceneTargets, toScenesBody, type SceneDraft } from './scenesForm';
import { addSprite, changeSprite, removeSprite, spriteDrafts, SPRITES_MAX, spritesHints, toSpritesBody, type SpriteDraft } from './spritesForm';

const IMG = '00000000-0000-4000-8000-0000000000c1';

describe('캐릭터 그림', () => {
  const smile: SpriteDraft = { id: 's1', imageId: IMG, expression: '웃음', outfit: '' };

  it('그림이 있어야 하고, 같은 표정(대소문자 무시)과 차림은 하나다', () => {
    expect(spritesHints([smile])).toEqual({});
    expect(spritesHints([{ ...smile, imageId: null }]).s1).toMatch(/그림을 올려/);
    expect(spritesHints([{ ...smile, expression: '가'.repeat(21) }]).s1).toMatch(/20자/);
    const twin = [
      { ...smile, expression: 'Smile' },
      { ...smile, id: 's2', expression: ' smile ' },
      { ...smile, id: 's3', expression: 'smile', outfit: 'coat' },
    ];
    expect(spritesHints(twin)).toEqual({ s2: expect.stringMatching(/이미 있습니다/) });
  });

  it('더하기, 바꾸기, 지우기와 보낼 때의 모양(처음 차림은 null)', () => {
    const full = Array.from({ length: SPRITES_MAX }, (_, i) => ({ ...smile, id: `s${i}` }));
    expect(addSprite(full, 'x')).toBe(full);
    expect(addSprite([], 's9')).toEqual([{ id: 's9', imageId: null, expression: '', outfit: '' }]);
    const sprites = changeSprite([smile, { ...smile, id: 's2', expression: '' }], 's2', { outfit: 'coat' });
    expect(removeSprite(sprites, 's1').map((sprite) => sprite.id)).toEqual(['s2']);
    expect(toSpritesBody([{ ...smile, expression: ' 웃음 ' }, ...sprites.slice(1)])).toEqual({
      sprites: [
        { id: 's1', image_id: IMG, expression: '웃음', outfit: null },
        { id: 's2', image_id: IMG, expression: '', outfit: 'coat' },
      ],
    });
    const character = { sprites: [{ id: 's1', image_id: IMG, expression: '웃음', outfit: null }] } as unknown as AssetCharacterDetail;
    expect(spriteDrafts(character)).toEqual([smile]);
  });
});

describe('이벤트 씬', () => {
  const beach: SceneDraft = { id: 'e1', title: '바닷가', imageId: IMG, description: '', collectible: true, kind: 'reach_place', target: 'p1' };

  it('제목, 그림, 대상이 있어야 하고 설명은 300자', () => {
    expect(scenesHints([beach])).toEqual({});
    expect(scenesHints([{ ...beach, title: ' ', imageId: null, target: '', description: '가'.repeat(301) }]).e1).toEqual({
      title: expect.any(String),
      image: expect.any(String),
      target: expect.any(String),
      description: expect.stringMatching(/300자/),
    });
    expect(scenesHints([{ ...beach, title: '가'.repeat(31) }]).e1?.title).toMatch(/30자/);
  });

  it('조건의 종류를 바꾸면 대상을 비운다. 같은 종류면 남긴다', () => {
    expect(changeScene([beach], 'e1', { kind: 'give_item' })[0]?.target).toBe('');
    expect(changeScene([beach], 'e1', { kind: 'reach_place', title: '해변' })[0]).toMatchObject({ target: 'p1', title: '해변' });
  });

  it('대상은 저장한 장소, 물건, 호감도 단계에서 고른다', () => {
    const character = {
      places: [{ id: 'p1', name: '' }],
      items: [{ id: 'i1', name: '꽃' }],
      affection: { stages: [{ name: '처음', at: 0 }, { name: '연인', at: 80 }] },
    } as unknown as AssetCharacterDetail;
    expect(sceneTargets(character, 'reach_place')).toEqual([{ value: 'p1', label: '장소 1' }]);
    expect(sceneTargets(character, 'give_item')).toEqual([{ value: 'i1', label: '꽃' }]);
    expect(sceneTargets(character, 'affection_stage').map((target) => target.value)).toEqual(['처음', '연인']);
    expect(sceneTargets({ ...character, affection: null }, 'affection_stage')).toEqual([]);
  });

  it('더하기와 보낼 때의 모양', () => {
    const full = Array.from({ length: SCENES_MAX }, (_, i) => ({ ...beach, id: `e${i}` }));
    expect(addScene(full, 'x')).toBe(full);
    expect(addScene([], 'e9')[0]).toEqual({ id: 'e9', title: '', imageId: null, description: '', collectible: true, kind: 'reach_place', target: '' });
    expect(toScenesBody([{ ...beach, title: ' 바닷가 ', description: ' 노을 ', collectible: false }])).toEqual({
      event_scenes: [{ id: 'e1', title: '바닷가', image_id: IMG, description: '노을', collectible: false, when: { kind: 'reach_place', target: 'p1' } }],
    });
    const character = { event_scenes: [{ id: 'e1', title: '바닷가', image_id: IMG, description: '', collectible: true, when: { kind: 'reach_place', target: 'p1' } }] } as unknown as AssetCharacterDetail;
    expect(sceneDrafts(character)).toEqual([beach]);
  });
});
