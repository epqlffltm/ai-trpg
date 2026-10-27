// web/apps/web/src/pages/story/StoryMapButton.tsx
// 지도(D3, 장면의 창). 지금 있는 곳과 함께 다니는 인물, 길로 바로 이어진 곳(걸리는 분, 닿는 시각, 거기 보이는 인물, "가기"),
// 그 밖에 아는 곳(가 본 곳, 거기 보이는 인물). 고르면 이동의 행동을 붙이고 반응을 받는다(한 번 청구).
// 거기 있는 인물은 서버가 보이기를 정해 보낸다. 받는 중이거나 끝난 세션이면 "가기"를 막는다.
// 기한의 마지막 날을 넘기는 이동이면 창 안에서 한 번 더 묻는다(넘기면 기한의 엔딩이다).

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { StoryAction, StoryState, StoryView } from '../../api/story';
import { destinations } from './storyActions';
import { arrivalText, companionNames, crossesDeadline, knownPlaces } from './storyMapView';
import { placeName } from './storyWorld';

type Props = { view: StoryView; state: StoryState; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

export function StoryMapButton({ view, state, disabled, onAct }: Props) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<{ id: string; name: string } | null>(null);
  const close = useCallback(() => {
    setOpen(false);
    setConfirming(null);
  }, []);
  const reachable = destinations(view, state.place);
  const known = knownPlaces(view, state);
  const others = known.filter((place) => !place.here && !reachable.some((entry) => entry.id === place.id));
  const castAt = (id: string) => known.find((place) => place.id === id)?.cast ?? [];
  const companions = companionNames(view, state);

  function go(place: string) {
    close();
    void onAct({ kind: 'move', place });
  }

  return (
    <>
      <Button variant="secondary" disabled={disabled} onClick={() => setOpen(true)}>
        지도
      </Button>
      <Dialog title="지도" open={open} onClose={close}>
        {confirming ? (
          <div className="story-places__confirm" role="alert">
            <p>
              {confirming.name}(으)로 가면 기한의 마지막 날을 넘깁니다. 기한이 지나면 기한의 엔딩이 열립니다.
            </p>
            <div className="actions">
              <Button disabled={disabled} onClick={() => go(confirming.id)}>
                그래도 가기
              </Button>
              <Button variant="quiet" onClick={() => setConfirming(null)}>
                그만두기
              </Button>
            </div>
          </div>
        ) : null}
        <p>지금 있는 곳: {placeName(view, state.place)}</p>
        {companions.length > 0 ? <p className="hint">함께: {companions.join(', ')}</p> : null}
        {reachable.length === 0 ? <p className="empty-state">여기서 바로 갈 수 있는 곳이 없습니다.</p> : null}
        <ul className="plain-list story-places" aria-label="갈 수 있는 곳">
          {reachable.map((place) => (
            <li key={place.id} className="story-places__row">
              <span>
                {place.name} <span className="hint">{place.minutes}분</span>
                <span className="hint story-places__detail">
                  {[
                    arrivalText(view, state, place.minutes),
                    crossesDeadline(view, state, place.minutes) ? '기한을 넘김' : null,
                    castAt(place.id).length > 0 ? `있음: ${castAt(place.id).join(', ')}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <Button
                variant="secondary"
                disabled={disabled}
                aria-label={`${place.name}(으)로 가기`}
                onClick={() => (crossesDeadline(view, state, place.minutes) ? setConfirming({ id: place.id, name: place.name }) : go(place.id))}
              >
                가기
              </Button>
            </li>
          ))}
        </ul>
        {others.length > 0 ? (
          <>
            <h3 className="story-places__title">아는 곳</h3>
            <ul className="plain-list story-places" aria-label="아는 곳">
              {others.map((place) => (
                <li key={place.id} className="story-places__row">
                  <span>
                    {place.name}
                    <span className="hint story-places__detail">
                      {[place.visited ? '가 본 곳' : null, place.cast.length > 0 ? `있음: ${place.cast.join(', ')}` : null].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </Dialog>
    </>
  );
}
