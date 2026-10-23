// web/apps/web/src/pages/chat/studio/characters/imagesForm.test.ts
// 그림 탭(C6)의 입력: 고친 것만 담기, 시간대의 배경을 붙이고 떼기, 보낼 때 최근의 장소·물건 목록에 그림 칸만 얹기.

import { describe, expect, it } from 'vitest';
import type { AssetCharacterDetail } from '../../../../api/types';
import { imagesDraft, itemImage, placeImages, setItemImage, setPlaceBackground, setPlaceDefault, timeLabel, toImagesBody } from './imagesForm';

const A = '00000000-0000-4000-8000-0000000000a1';
const B = '00000000-0000-4000-8000-0000000000b1';

function character(extra: Record<string, unknown> = {}) {
  return {
    image_id: null,
    places: [{ id: 'p1', name: '집', description: '', image_id: A, backgrounds: { night: A } }],
    items: [{ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: null }],
    ...extra,
  } as unknown as AssetCharacterDetail;
}

describe('그림 탭', () => {
  it('고치지 않은 것은 받은 그대로 보인다', () => {
    const draft = imagesDraft(character({ image_id: A }));
    expect(draft).toEqual({ imageId: A, places: {}, items: {} });
    expect(placeImages(draft, character(), 'p1')).toEqual({ image_id: A, backgrounds: { night: A } });
    expect(itemImage(draft, character(), 'i1')).toBeNull();
    expect(placeImages(draft, character(), 'gone')).toEqual({ image_id: null, backgrounds: {} });
  });

  it('시간대의 배경을 붙이고 떼고, 기본 배경을 바꾼다', () => {
    const base = character();
    let draft = setPlaceBackground(imagesDraft(base), base, 'p1', 'dawn', B);
    expect(placeImages(draft, base, 'p1').backgrounds).toEqual({ night: A, dawn: B });
    draft = setPlaceBackground(draft, base, 'p1', 'night', null);
    expect(placeImages(draft, base, 'p1').backgrounds).toEqual({ dawn: B });
    draft = setPlaceDefault(draft, base, 'p1', null);
    expect(placeImages(draft, base, 'p1')).toEqual({ image_id: null, backgrounds: { dawn: B } });
    expect(timeLabel('evening')).toBe('저녁');
  });

  it('보낼 때 최근의 목록에 그림 칸만 얹는다. 지도 탭이 그사이 고친 이름과 새 장소를 되돌리지 않는다', () => {
    const opened = character();
    const draft = setItemImage(setPlaceBackground(imagesDraft(opened), opened, 'p1', 'day', B), 'i1', B);
    const latest = character({
      places: [
        { id: 'p1', name: '우리 집', description: '바뀐 설명', image_id: A, backgrounds: { night: A } },
        { id: 'p2', name: '새 곳', description: '', image_id: null, backgrounds: {} },
      ],
    });

    expect(toImagesBody({ ...draft, imageId: B }, latest)).toEqual({
      image_id: B,
      places: [
        { id: 'p1', name: '우리 집', description: '바뀐 설명', image_id: A, backgrounds: { night: A, day: B } },
        { id: 'p2', name: '새 곳', description: '', image_id: null, backgrounds: {} },
      ],
      items: [{ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: B }],
    });
  });

  it('그사이 지운 장소의 그림 칸은 보내지 않는다', () => {
    const opened = character();
    const draft = setPlaceDefault(imagesDraft(opened), opened, 'p1', B);
    expect(toImagesBody(draft, character({ places: [] })).places).toEqual([]);
  });
});
