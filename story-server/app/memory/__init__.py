# story-server/app/memory/__init__.py

"""
기억 메모(화면 명세의 D2 의 창, chat 의 C5 와 같다). 사람이 쓴 짧은 글을 모델에 늘 보낸다.

    models.py      memory_notes 표
    schemas.py     API 의 입력과 응답
    repository.py  읽고 쓰기(커밋하지 않는다)
    service.py     세션의 주인만 보고 고친다. 수의 상한을 지킨다. 카드의 [기억] 블록을 만든다
    router.py      /conversations/{id}/notes

굴리는 요약과 요약이 제안하는 메모(chat 의 #677)는 아직 없다.
"""
