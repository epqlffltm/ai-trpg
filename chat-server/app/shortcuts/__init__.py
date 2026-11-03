# chat-server/app/shortcuts/__init__.py

"""
대화의 단축어(#981). 사람의 말이 "/이름"으로 시작하면 정해 둔 연출의 글을 그 턴의 프롬프트에만 붙인다.

  - calls.py: 말에서 부른 이름을 떼고, 찾고, 모델에 보낼 글을 만든다. DB 도 바깥도 모른다
  - service.py: 내 단축어를 asset 서버에서 가져온다(이름을 부른 말에만)

단축어의 모양과 상한은 asset 서버가 지킨다(asset-server 의 app/shortcuts/schemas.py).
"""
