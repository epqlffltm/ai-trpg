# asset-server/app/shortcuts/__init__.py

"""
단축어(#981). 대화 중에 "/이름"으로 부르면 미리 적은 연출의 글이 그 턴에만 붙는다.

  - 제작자 단축어: 캐릭터와 세계관의 초안에 적고, 게시하면 판의 문서에 굳는다(characters, worlds 가 이 모양을 쓴다)
  - 내 단축어: 계정의 것이다. 어느 작품에서든 쓴다(models, repository, service, router)
  - 다른 서버(chat, story)는 말을 보낼 때 내 단축어를 가져간다(supply)
모양과 상한은 schemas.py 하나에 둔다. 셋이 같은 규칙을 쓴다.
"""
