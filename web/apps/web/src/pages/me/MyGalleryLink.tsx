// web/apps/web/src/pages/me/MyGalleryLink.tsx
// 마이페이지의 "갤러리". 내가 연 일러스트(C7)로 가는 길.

import { Link } from 'react-router';

export function MyGalleryLink() {
  return (
    <section className="page-section" aria-labelledby="my-gallery-heading">
      <h2 id="my-gallery-heading">갤러리</h2>
      <p>
        <Link to="/gallery">내가 연 일러스트</Link>
      </p>
    </section>
  );
}
