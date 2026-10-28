# story-server/app/lore/__init__.py

"""
세계관의 로어북을 뜻으로 찾는다(하이브리드의 벡터 쪽). chat 서버의 app/lore 와 같은 모양이다.

    texts.py     판에서 항목을 꺼내고, 벡터로 바꿀 글을 만든다(순수 함수)
    models.py    항목의 벡터(lore_embeddings)
    repository   벡터를 읽고 쓴다
    indexing.py  모자란 벡터를 따로 도는 작업으로 채운다
    recall.py    말 한 번에 한 번, 최근 말과 가까운 항목을 찾는다
    setup.py     설정으로 임베더를 고른다

상시와 키워드로 고르는 쪽은 app/turns/service.py 의 lore_plan_of 가 한다(conversation_core/lorebook.py).
"""
