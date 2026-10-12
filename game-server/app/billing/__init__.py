# game-server/app/billing/__init__.py

"""
라운드의 서술 값을 결제 서버에서 받는다(#148).

라운드를 열 때 그 라운드의 서술 값을 결제 서버에 미리 잡아 두고(홀드), 서술이 끝나 다음 장면이 되면 확정하고,
서술 없이 끝난 라운드(테이블이 끝났다)는 돌려준다.
크레딧의 잔액과 원장은 결제 서버만 안다. 게임 서버는 묻고 맡길 뿐이다.

  - client.py: 결제 서버를 부르는 것의 모양(Billing)과 결과
  - http_billing.py: 실제로 결제 서버를 부르는 것. 요청에 서명한다(signing.py)
  - free_billing.py: 받지 않는 것. BILLING_URL 을 비우면 이것이다
  - models.py, repository.py: 청구 기록(narration_charges). 라운드마다 무엇을 잡았고 어떻게 끝내야 하는지
  - charges.py: 청구 기록을 만들고 상태를 옮기는 규칙
  - settling.py: 청구 하나를 결제 서버에 맡기고 그 결과를 적는 일
  - settler.py: 몇 초마다 끝나지 않은 청구를 마저 끝내는 작업
"""
