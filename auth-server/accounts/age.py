# auth-server/accounts/age.py

"""
나이의 날짜 계산(#336). DB 를 보지 않는다. 받은 날짜만으로 답한다.

나이를 가르는 날이 법마다 다르다.
  - 민법(4조): 만 19세 생일부터 성년이다. 결제(계약)는 이 날을 본다
  - 청소년 보호법(2조): 만 19세가 되는 해의 1월 1일부터 청소년이 아니다. 성인용 내용은 이 날을 본다
  - 개인정보 보호법(22조의2): 만 14세 미만은 보호자의 동의 없이 개인정보를 모을 수 없다

"오늘" 은 한국 날짜다. 서버의 시각은 UTC 라(settings.TIME_ZONE) 그대로 날짜를 자르면 아침 9시까지 하루가 늦다.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

# 날짜를 자르는 곳의 시간대. 사용자가 사는 곳이다
KOREA = ZoneInfo('Asia/Seoul')

# 민법의 성년. 청소년 보호법도 같은 나이를 쓴다(날짜만 다르다)
ADULT_AGE = 19
# 이 나이가 안 되면 보호자의 동의 없이 개인정보를 모을 수 없다. 이 서비스는 받지 않는다
MIN_AGE = 14


def korean_today(now: datetime | None = None) -> date:
    """한국의 오늘 날짜. now 를 주지 않으면 지금이다."""
    return (now or timezone.now()).astimezone(KOREA).date()


def years_after(birth_date: date, years: int) -> date:
    """
    만 years 세가 되는 날. 태어난 날의 years 년 뒤 같은 날이다.

    2월 29일에 태어났고 그해에 2월 29일이 없으면 3월 1일이다. 민법은 나이를 셀 때 태어난 날을 넣고(158조)
    마지막 해에 같은 날이 없으면 그 달의 말일(2월 28일)로 기간이 끝난다(160조). 그다음 날부터 그 나이다.
    """
    try:
        return birth_date.replace(year=birth_date.year + years)
    except ValueError:
        return date(birth_date.year + years, 3, 1)


def legal_adult_from(birth_date: date) -> date:
    """민법의 성년이 되는 날. 만 19세 생일이다."""
    return years_after(birth_date, ADULT_AGE)


def adult_content_from(birth_date: date) -> date:
    """성인용 내용을 볼 수 있게 되는 날. 만 19세가 되는 해의 1월 1일이다."""
    return date(birth_date.year + ADULT_AGE, 1, 1)


def is_under_min_age(birth_date: date, today: date) -> bool:
    """today 에 만 14세가 안 되었는가."""
    return today < years_after(birth_date, MIN_AGE)


def has_reached(day: date | None, today: date) -> bool:
    """
    그날이 왔는가. 비어 있으면 이미 지난 것으로 본다.

    본인인증 때 이미 지난 날은 적지 않는다(models.IdentityVerification). 성인의 생일을 남기지 않기 위해서다.
    """
    return day is None or day <= today
