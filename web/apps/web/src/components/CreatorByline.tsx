// web/apps/web/src/components/CreatorByline.tsx
// 작품 소개의 "만든 사람"(#992). 이름(닉네임)은 인증 서버에 공개 ID 로 묻고, 누르면 제작자 페이지로 간다.
// 이름을 아직 모르면 아무것도 그리지 않는다. 탈퇴한 사용자면 이름만 보이고 잇지 않는다(제작자 페이지가 404 다).

import { Link } from 'react-router';
import { UNKNOWN_PERSON, usePublicNames } from '../hooks/usePublicNames';

type Props = { creatorId: string; className?: string };

export function CreatorByline({ creatorId, className = 'hint' }: Props) {
  const name = usePublicNames([[creatorId]])(creatorId);
  if (name === undefined) return null;
  return (
    <p className={className}>
      만든 사람 {name === UNKNOWN_PERSON ? name : <Link to={`/creators/${encodeURIComponent(creatorId)}`}>{name}</Link>}
    </p>
  );
}
