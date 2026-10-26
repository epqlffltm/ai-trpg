# story-server/app/records/__init__.py

"""
계정의 기록(docs/architecture/story.md 의 "세션과 기록"). 세션을 지우거나 가지를 바꿔도 남는다.

  - models.py, repository.py: 본 엔딩(ending_records)과 연 일러스트(illustration_unlocks).
    본 엔딩은 사람마다, 세계관마다, 엔딩마다 한 줄이고, 연 일러스트는 사람마다, 세계관마다, 장면마다 한 줄이다
  - illustrations.py: 행동 뒤에 열린 이벤트와 본 엔딩 가운데 계정에 남길 장면을 고른다. DB 를 모른다
  - router.py, schemas.py: 내가 본 엔딩의 목록(엔딩 목록 화면 D6)과 연 일러스트의 목록(갤러리의 story 탭 C7)

연 일러스트의 키는 세계관과 장면이다(2026-10-26). 일러스트는 인물이 아니라 이벤트와 엔딩의 장면에 붙어 있고,
한 장면에 인물이 0~4 명이라 인물 하나로 가리킬 수 없다. 장면이 부르는 인물은 칸(cast)으로 함께 적어
갤러리가 "세계관마다, 그 안의 인물마다" 묶는다. 인물이 없는 장면은 세계관 칸에 든다.
"""
