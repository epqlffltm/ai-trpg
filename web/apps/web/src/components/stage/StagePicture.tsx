// web/apps/web/src/components/stage/StagePicture.tsx
// 그림 창(미연시의 구조). chat 의 대화(C3), story 의 장면(D2)이 함께 쓰고, TRPG 의 테이블 방(#1163)도 쓴다.
//   - 무대(stage): 지금 장소(와 시간대)의 배경 위에 인물(children)을 겹친다
//   - 컷신(scene): 이벤트·엔딩의 통짜 그림이 열렸으면 그것을 띄운다. 인물(children)은 그 아래에 둔다(쓰는 쪽이 비울 수 있다)
//   - 그림 없음(none): 그림 창 없이 인물만 둔다. framed 면 배경이 없어도 빈 무대를 둔다(chat 은 늘 캐릭터 그림을 세운다)
// 무엇을 띄울지(장면, 배경, 인물)는 쓰는 쪽이 게임 상태로 고른다. 여기는 그리기만 한다. 그림은 토큰을 실어 받는다(성인 등급의 그림).
// 그림은 늦게 오므로, 인물은 그림이 오기 전과 뒤에 늘 같은 자리(같은 틀의 마지막)에 둔다.
// 자리가 바뀌면 인물 줄이 새로 그려져 열어 둔 창(story 의 인물 창)이 닫히기 때문이다. 모드는 틀의 class 로만 바꾼다.
// 겹칠 것(overlay, story 의 이벤트 선택지)은 컷신이면 그림의 틀 안에, 아니면 인물 바로 앞에 둔다(넓으면 그림 위, 좁으면 그림 아래. CSS).

import type { ReactNode } from 'react';
import { useImageUrl } from '../../hooks/useImageUrl';

type Props = {
  /** 열린 통짜 그림(이벤트, 엔딩). 없으면 null */
  scene: { title: string; imageId: string } | null;
  /** 지금 장소의 배경 그림. 없으면 null */
  background: string | null;
  /** 배경 그림의 대체 글(장소의 이름) */
  placeName: string;
  /** 배경이 없어도 빈 무대를 둘까 */
  framed?: boolean;
  /** 그림 위에 겹칠 것. 없으면 null */
  overlay?: ReactNode;
  children?: ReactNode;
};

/** 그림 창의 모드. 컷신(아래에 인물), 무대(배경 위에 인물), 그림 없음(인물만) */
export type PictureMode = 'scene' | 'stage' | 'none';

export function pictureMode(hasImage: boolean, hasScene: boolean, framed = false): PictureMode {
  if (hasImage && hasScene) return 'scene';
  if (hasImage || framed) return 'stage';
  return 'none';
}

export function StagePicture({ scene, background, placeName, framed = false, overlay = null, children }: Props) {
  const image = useImageUrl(scene?.imageId ?? background);
  const mode = pictureMode(Boolean(image.url), scene !== null, framed);
  const pictured = mode !== 'none';
  return (
    <div className={`stage-picture stage-picture--${mode}`} role={pictured ? 'figure' : undefined} aria-label={pictured ? '그림 창' : undefined}>
      {mode === 'scene' && scene ? (
        <div className="stage-picture__frame">
          <img src={image.url ?? undefined} alt={scene.title} className="stage-picture__image" />
          <p className="stage-picture__caption">{scene.title}</p>
          {overlay ? <div className="stage-picture__overlay">{overlay}</div> : null}
        </div>
      ) : mode === 'stage' && image.url ? (
        <img src={image.url} alt={placeName} className="stage-picture__image" />
      ) : null}
      {overlay && mode !== 'scene' ? <div className="stage-picture__overlay">{overlay}</div> : null}
      {children}
    </div>
  );
}
