// web/apps/web/src/pages/home/ServicePicker.tsx
// 서비스 고르기. TRPG, chat, story 셋이다.
// 카드 위의 그림 띠(기호)는 꾸밈이라 화면 낭독기에는 숨긴다. 이름과 한 줄 머리말, 설명만 읽힌다.

import { Link } from 'react-router';

const SERVICES = [
  { to: '/trpg', key: 'trpg', mark: '⚄', kicker: '여럿이 함께', name: 'TRPG', description: '여럿이 한 테이블에 앉아 AI 진행자와 시나리오를 함께 푼다' },
  { to: '/chat', key: 'chat', mark: '♡', kicker: '1:1 대화', name: 'chat', description: '캐릭터 하나와 1:1 로 이야기한다' },
  { to: '/story', key: 'story', mark: '✧', kicker: '혼자 걷는 이야기', name: 'story', description: '혼자 세계관을 걸으며 여러 인물을 만나는 이야기' },
] as const;

export function ServicePicker() {
  return (
    <nav aria-label="서비스" className="service-picker">
      {SERVICES.map((service) => (
        <Link key={service.to} to={service.to} className={`service-card service-card--${service.key}`}>
          <span className="service-card__art" aria-hidden="true">
            {service.mark}
          </span>
          <span className="service-card__body">
            <span className="service-card__kicker">{service.kicker}</span>
            <span className="service-card__name">{service.name}</span>
            <span className="service-card__description">{service.description}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}
