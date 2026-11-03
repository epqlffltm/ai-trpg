# story-server/app/shortcuts/__init__.py

"""
세션의 단축어(#981). 사람의 말이 "/이름"으로 시작하면 정해 둔 연출의 글을 그 턴의 프롬프트에만 붙인다.

  - calls.py: 말에서 부른 이름을 떼고, 찾고, 모델에 보낼 글을 만든다. DB 도 바깥도 모른다
  - service.py: 내 단축어를 asset 서버에서 가져오고, 세션에서 고를 수 있는 단축어를 모은다
  - schemas.py, router.py: 고를 수 있는 단축어의 목록 API

단축어의 모양과 상한은 asset 서버가 지킨다(asset-server 의 app/shortcuts/schemas.py). chat 서버의 것과 같은 규칙이다.
"""
