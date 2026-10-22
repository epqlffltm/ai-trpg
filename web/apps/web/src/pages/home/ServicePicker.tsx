// web/apps/web/src/pages/home/ServicePicker.tsx
// 서비스 고르기. TRPG, chat, story 셋이다. story 는 서버가 아직 없어 "준비 중"이다.

import { Link } from 'react-router';

const SERVICES = [
  { to: '/trpg', name: 'TRPG', description: '여럿이 한 테이블에 앉아 AI 진행자와 시나리오를 함께 푼다' },
  { to: '/chat', name: 'chat', description: '캐릭터 하나와 1:1 로 이야기한다' },
  { to: '/story', name: 'story', description: '혼자 세계관을 걷는 이야기. 준비 중' },
] as const;

export function ServicePicker() {
  return (
    <nav aria-label="서비스" className="service-picker">
      {SERVICES.map((service) => (
        <Link key={service.to} to={service.to} className="service-card">
          <span className="service-card__name">{service.name}</span>
          <span className="service-card__description">{service.description}</span>
        </Link>
      ))}
    </nav>
  );
}
