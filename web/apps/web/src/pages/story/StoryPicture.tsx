// web/apps/web/src/pages/story/StoryPicture.tsx
// 그림 창(D2 의 위, Stitch 22번). 이벤트나 엔딩의 일러스트가 열렸으면 그것을 띄우고, 장면의 인물 줄(children)은 그 아래에 둔다.
// 일러스트가 없으면 지금 장소와 시간대의 배경을 깔고 그 위에 장면의 인물 줄을 겹친다(인물을 나란히 세우는 무대).
// 그림은 토큰을 실어 받는다. 그림이 없거나 받지 못하면 그림 창 없이 인물 줄만 둔다.
// 그림은 늦게 오므로, 인물 줄은 그림이 오기 전과 뒤에 늘 같은 자리(같은 틀의 마지막)에 둔다.
// 자리가 바뀌면 인물 줄이 새로 그려져 열어 둔 인물 창이 닫히기 때문이다. 모드는 틀의 class 로만 바꾼다.

import type { ReactNode } from 'react';
import { useImageUrl } from '../../hooks/useImageUrl';

type Props = { scene: { title: string; imageId: string } | null; background: string | null; placeName: string; children?: ReactNode };

/** 그림 창의 모드. 일러스트(아래에 인물 줄), 무대(배경 위에 인물 줄), 그림 없음(인물 줄만) */
export type PictureMode = 'scene' | 'stage' | 'none';

export function pictureMode(hasImage: boolean, hasScene: boolean): PictureMode {
  if (!hasImage) return 'none';
  return hasScene ? 'scene' : 'stage';
}

export function StoryPicture({ scene, background, placeName, children }: Props) {
  const image = useImageUrl(scene?.imageId ?? background);
  const mode = pictureMode(Boolean(image.url), scene !== null);
  const pictured = mode !== 'none';
  return (
    <div
      className={`story-picture story-picture--${mode}`}
      role={pictured ? 'figure' : undefined}
      aria-label={pictured ? '그림 창' : undefined}
    >
      {mode === 'scene' && scene ? (
        <div className="story-picture__frame">
          <img src={image.url ?? undefined} alt={scene.title} className="story-picture__image" />
          <p className="story-picture__caption">{scene.title}</p>
        </div>
      ) : mode === 'stage' ? (
        <img src={image.url ?? undefined} alt={placeName} className="story-picture__image" />
      ) : null}
      {children}
    </div>
  );
}
