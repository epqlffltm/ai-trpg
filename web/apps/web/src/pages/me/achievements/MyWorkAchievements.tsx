// web/apps/web/src/pages/me/achievements/MyWorkAchievements.tsx
// 마이페이지 설정 탭의 "작품 업적"(#193). 제작자가 작품에 단 업적 가운데 내가 받은 것을 서비스마다(TRPG, 스토리, 채팅) 모아 본다.
// 활동 배지(인증 서버)와는 다른 것이다. 고른 서비스의 서버만 부른다. 받은 때가 늦은 것부터 한 쪽씩, "더 보기"로 이어 읽는다.
// 줄마다 업적의 그림, 이름, 받는 법, 작품의 이름(소개로 가는 길), 받은 날. 읽지 못하면 다시 시도를 둔다.
// 고른 서비스는 이 화면에만 둔다(주소에 두지 않는다). 업적을 주는 것은 각 서버의 엔진이다. 화면은 읽기만 한다.

import { Button, ChipGroup, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { useImageUrl } from '../../../hooks/useImageUrl';
import { Avatar, ListingAvatar } from '../../trpg/portraits/CharacterAvatar';
import { myAchievementsQuery } from './myAchievementsQueries';
import { earnedOn, SERVICE_TABS, totalLine, type AchievementImage, type AchievementService, type MyAchievementLine } from './myAchievementsView';

export function MyWorkAchievements() {
  const [service, setService] = useState<AchievementService>('trpg');
  return (
    <section className="page-section" aria-labelledby="my-work-achievements-heading">
      <h2 id="my-work-achievements-heading">작품 업적</h2>
      <p className="hint">시나리오, 세계관, 캐릭터를 만든 사람이 단 업적 가운데 내가 받은 것입니다. 받은 때가 늦은 것부터 보입니다.</p>
      <ChipGroup label="서비스" chips={SERVICE_TABS} selected={service} onChange={(next) => setService((current) => next ?? current)} />
      <ServiceAchievements key={service} service={service} />
    </section>
  );
}

function ServiceAchievements({ service }: { service: AchievementService }) {
  const query = useInfiniteQuery(myAchievementsQuery(service));
  const lines = query.data?.pages.flatMap((page) => page.lines) ?? [];
  const total = query.data?.pages.at(-1)?.total ?? 0;
  if (query.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (query.isError && lines.length === 0) {
    return (
      <Notice tone="error">
        작품 업적을 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void query.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  if (lines.length === 0) return <p>아직 받은 업적이 없습니다.</p>;
  return (
    <>
      <p>{totalLine(service, total)}</p>
      <ul className="plain-list achievement-list" aria-label="받은 작품 업적">
        {lines.map((line) => (
          <AchievementLine key={line.key} line={line} />
        ))}
      </ul>
      {query.hasNextPage ? (
        <p>
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </p>
      ) : null}
      {query.isFetchNextPageError ? <p className="ui-field__error">더 불러오지 못했습니다. 다시 눌러 주세요.</p> : null}
    </>
  );
}

function AchievementLine({ line }: { line: MyAchievementLine }) {
  return (
    <li className="achievement-item">
      <AchievementPicture image={line.image} name={line.name} />
      <div className="achievement-item__body">
        <strong>{line.name}</strong>
        {line.description ? <span>{line.description}</span> : null}
        <span className="hint">{line.workLink ? <Link to={line.workLink}>{line.workName}</Link> : line.workName}</span>
        <span className="hint">{earnedOn(line)}</span>
      </div>
    </li>
  );
}

function AchievementPicture({ image, name }: { image: AchievementImage; name: string }) {
  if (image?.kind === 'listing') return <ListingAvatar scenarioId={image.scenarioId} portraitId={image.imageId} name={name} />;
  return <AssetPicture imageId={image?.imageId ?? null} name={name} />;
}

function AssetPicture({ imageId, name }: { imageId: string | null; name: string }) {
  const image = useImageUrl(imageId);
  return <Avatar name={name} url={image.url} />;
}
