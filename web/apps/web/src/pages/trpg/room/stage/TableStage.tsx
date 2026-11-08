// web/apps/web/src/pages/trpg/room/stage/TableStage.tsx
// 테이블 방의 그림 창(#1163). 장소의 배경 위에 장면의 인물을 세우고, 사건이 일어나거나 퀘스트를 이루면 컷신을 띄운다.
// 무엇을 띄울지는 tableStageView.ts 가 고른다. 그림은 테이블의 그림 주소로 토큰을 실어 받는다(tablePortraitImageQuery).
// 띄울 그림이 하나도 없으면(그림을 붙이지 않은 판) 그리지 않는다.
// 테이블, 장면, 이벤트는 방이 읽는 것을 함께 쓴다. 이벤트가 오면 방이 테이블과 라운드를 다시 읽으므로 배경과 인물도 따라 바뀐다.

import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { StageFrame } from '../../../../components/stage/StagePicture';
import { tablePortraitImageQuery } from '../../portraits/portraitQueries';
import { useBlobUrl } from '../../portraits/useBlobUrl';
import { sceneCastQuery } from '../round/roundQueries';
import { eventsQuery } from '../roomQueries';
import { stageCutscene, stagePeople, stagePlace, type StagePerson } from './tableStageView';

export function TableStage({ table }: { table: TableDetail }) {
  const playing = table.status === 'playing';
  const cast = useQuery({ ...sceneCastQuery(table.id), enabled: playing });
  const events = useQuery(eventsQuery(table.id));
  const place = stagePlace(table.map, table.members);
  const people = playing ? stagePeople(cast.data, place?.id ?? null) : [];
  const cutscene = stageCutscene(events.data?.items ?? []);
  const shownImage = cutscene?.imageId ?? place?.imageId ?? null;
  const image = useTablePicture(table.id, shownImage);

  if (shownImage === null && people.length === 0) return null;
  return (
    <StageFrame scene={cutscene} imageUrl={image} placeName={place?.name ?? '장소'} framed={people.length > 0}>
      {cutscene === null && people.length > 0 ? <StagePeople tableId={table.id} people={people} /> : null}
    </StageFrame>
  );
}

/** 배경 위에 나란히 세운 인물 */
function StagePeople({ tableId, people }: { tableId: string; people: StagePerson[] }) {
  return (
    <section className="story-cast" aria-label="장면의 인물">
      <ul className="plain-list story-cast__list">
        {people.map((person) => (
          <li key={person.id} className="story-cast__member">
            <PersonPicture tableId={tableId} person={person} />
            <span className="story-cast__name">{person.name}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PersonPicture({ tableId, person }: { tableId: string; person: StagePerson }) {
  const url = useTablePicture(tableId, person.imageId);
  return url ? <img className="story-cast__portrait" src={url} alt={person.name} /> : <span className="story-cast__portrait" aria-hidden="true" />;
}

/** 테이블의 그림 하나의 주소. 없거나 받기 전이면 null */
function useTablePicture(tableId: string, imageId: string | null): string | null {
  const image = useQuery({ ...tablePortraitImageQuery(tableId, imageId ?? ''), enabled: imageId !== null });
  return useBlobUrl(imageId === null ? undefined : image.data);
}
