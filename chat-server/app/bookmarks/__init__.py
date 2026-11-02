# chat-server/app/bookmarks/__init__.py

"""
말의 책갈피(#982). 대화의 말 하나에 책갈피를 달고(짧은 메모를 붙일 수 있다), 대화마다 목록을 본다.

  - models.py: 책갈피의 테이블(bookmarks)
  - schemas.py: API 의 입력과 응답의 모양
  - repository.py: 쿼리. 커밋하지 않는다
  - service.py: 대화의 주인만, 그 대화의 말만, 대화마다 개수 상한
  - router.py: API
"""
