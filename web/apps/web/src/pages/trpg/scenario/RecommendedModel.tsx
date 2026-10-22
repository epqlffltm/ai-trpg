// web/apps/web/src/pages/trpg/scenario/RecommendedModel.tsx
// 소개(B2)의 추천 서술 모델. 시나리오는 이름표(slug)만 준다. 보일 이름은 서술 모델의 목록에서 찾는다.
// 그 목록은 로그인한 사람에게만 보인다(값 수집 막기). 로그인하지 않았으면 이 줄을 보이지 않는다.
// 목록에 없으면 지금 팔지 않는 모델이다. 테이블을 만들 때 같은 회사의 대신 쓸 모델로 정해진다(화면 명세 B2).

import { useQuery } from '@tanstack/react-query';
import { useSession } from '../../../auth/useSession';
import { narrationModelsQuery } from '../queries';

export function RecommendedModel({ slug }: { slug: string | null }) {
  const signedIn = useSession() !== null;
  if (!slug || !signedIn) return null;
  return <SignedInModel slug={slug} />;
}

function SignedInModel({ slug }: { slug: string }) {
  const models = useQuery(narrationModelsQuery());
  if (!models.isSuccess) return null;
  const model = models.data.models.find((candidate) => candidate.slug === slug);
  return (
    <>
      <dt>추천 서술 모델</dt>
      <dd>{model ? model.display_name : '지금은 쓸 수 없음(만들 때 비슷한 모델로 정해집니다)'}</dd>
    </>
  );
}
