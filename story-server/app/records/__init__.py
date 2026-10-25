# story-server/app/records/__init__.py

"""
계정의 기록(docs/architecture/story.md 의 "세션과 기록"). 세션을 지우거나 가지를 바꿔도 남는다.

  - models.py, repository.py: 본 엔딩(ending_records). 사람마다, 세계관마다, 엔딩마다 한 줄이다
  - router.py, schemas.py: 내가 본 엔딩의 목록(엔딩 목록 화면 D6 이 읽는다)

연 일러스트(illustration_unlocks)는 그 키(세계관의 그림인가 캐릭터의 그림인가)를 정한 뒤에 더한다.
"""
