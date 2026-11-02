# story-server/app/bookmarks/__init__.py

"""
말의 책갈피(#982). 세션의 말 하나에 책갈피를 달고(짧은 메모를 붙일 수 있다), 세션마다 목록을 본다.

  - models.py: 책갈피의 테이블(bookmarks)
  - schemas.py: API 의 입력과 응답의 모양
  - repository.py: 쿼리. 커밋하지 않는다
  - service.py: 세션의 주인만, 그 세션의 말만, 세션마다 개수 상한
  - router.py: API
"""
