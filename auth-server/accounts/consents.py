# auth-server/accounts/consents.py

"""
이용약관과 개인정보 수집·이용 같은 동의를 받고 기록한다(#450).

  - 항목마다 지금의 판(번호와 시행일)과 필수 여부를 이 파일의 표(POLICIES)에 둔다. 판을 올리는 것은 PR 이다
  - 가입을 마칠 때 필수 항목(이용약관, 개인정보 수집·이용)에 지금의 판으로 동의해야 한다. 선택 항목은 따로 받는다
  - 기록은 덮어쓰지 않고 쌓는다(ConsentRecord). 항목마다 마지막 줄이 지금의 상태다
  - 선택 항목은 언제든 동의하고 철회한다. 필수 항목은 철회하지 못한다(탈퇴로 한다)
  - 필수 항목의 판이 오르면(중요한 변경) 다시 동의해야 한다. 동의하기 전까지 access 토큰이 인증 서버에만 통한다
    (accounts/tokens.py 의 audience_for). 다른 서버의 API 는 막힌다. 토큰의 응답과 /me 의 consents_pending 이 알린다

중요하지 않은 고침(맞춤법, 연락처)은 판을 올리지 않는다. 판을 올리면 모두가 다시 동의해야 한다.
문서의 글은 여기 두지 않는다. 화면이 항목과 판으로 보인다.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType

from accounts.models import ConsentAction, ConsentItem, ConsentRecord, User


@dataclass(frozen=True)
class Policy:
    """항목 하나의 지금의 판."""

    item: str
    version: int
    effective_on: date
    required: bool


# 항목마다 지금의 판. 1판은 변호사 검토 전 초안의 판이다(#450). 문서가 확정되면 판을 올린다
POLICIES: Mapping[str, Policy] = MappingProxyType(
    {
        ConsentItem.TERMS: Policy(ConsentItem.TERMS, 1, date(2026, 10, 20), required=True),
        ConsentItem.PRIVACY: Policy(ConsentItem.PRIVACY, 1, date(2026, 10, 20), required=True),
        ConsentItem.MARKETING: Policy(ConsentItem.MARKETING, 1, date(2026, 10, 20), required=False),
        ConsentItem.AI_TRAINING: Policy(ConsentItem.AI_TRAINING, 1, date(2026, 10, 20), required=False),
    }
)


@dataclass(frozen=True)
class ConsentState:
    """한 사람의 항목 하나의 지금 상태. 동의하지 않았거나 철회했으면 agreed_version 과 agreed_at 이 없다."""

    item: str
    required: bool
    version: int
    agreed_version: int | None
    agreed_at: datetime | None

    @property
    def pending(self) -> bool:
        """필수 항목인데 지금의 판에 동의하지 않았다. 다시 동의를 받아야 한다."""
        return self.required and self.agreed_version != self.version


class UnknownConsentItemError(Exception):
    """표에 없는 항목이다."""


class ConsentOutdatedError(Exception):
    """지금의 판이 아닌 판에 동의하려 했다. 화면이 옛 문서를 보였다."""


class ConsentRequiredError(Exception):
    """필수 항목을 철회하려 했다."""


def policy_of(item: str) -> Policy:
    """그 항목의 지금의 판. 표에 없으면 UnknownConsentItemError."""
    policy = POLICIES.get(item)
    if policy is None:
        raise UnknownConsentItemError
    return policy


def signup_consent_problems(consents: Mapping[str, int]) -> list[str]:
    """
    가입 때 받은 동의(항목 → 판)의 문제들. 없으면 빈 목록이다.

    표에 없는 항목, 지금의 판이 아닌 판, 빠진 필수 항목을 본다. 선택 항목은 없어도 된다(동의하지 않은 것이다).
    """
    problems = [f'모르는 동의 항목입니다: {item}' for item in sorted(consents) if item not in POLICIES]
    problems += [
        f'{item} 의 판이 바뀌었습니다. 다시 읽고 동의해 주세요.'
        for item, version in sorted(consents.items())
        if item in POLICIES and POLICIES[item].version != version
    ]
    missing = sorted(item for item, policy in POLICIES.items() if policy.required and item not in consents)
    if missing:
        problems.append(f'필수 동의가 없습니다: {", ".join(missing)}')
    return problems


def record_signup_consents(user: User, consents: Mapping[str, int], now: datetime) -> None:
    """
    가입 때 받은 동의를 적는다. 검증(signup_consent_problems)을 지난 것만 넘긴다.

    계정을 만드는 트랜잭션 안에서 부른다.
    """
    ConsentRecord.objects.bulk_create(
        ConsentRecord(user=user, item=item, version=version, action=ConsentAction.AGREED, at=now)
        for item, version in sorted(consents.items())
    )


def latest_records(user: User) -> dict[str, ConsentRecord]:
    """항목마다 마지막 줄. 한 사람의 줄은 몇 개뿐이라 모두 읽어 고른다."""
    latest: dict[str, ConsentRecord] = {}
    for record in ConsentRecord.objects.filter(user=user).order_by('at', 'id'):
        latest[record.item] = record
    return latest


def state_of(policy: Policy, latest: ConsentRecord | None) -> ConsentState:
    """지금의 판과 마지막 줄로 항목 하나의 상태를 만든다."""
    agreed = latest is not None and latest.action == ConsentAction.AGREED
    return ConsentState(
        item=policy.item,
        required=policy.required,
        version=policy.version,
        agreed_version=latest.version if agreed else None,
        agreed_at=latest.at if agreed else None,
    )


def consent_states(user: User) -> list[ConsentState]:
    """그 사람의 항목마다의 상태. 표의 차례다."""
    latest = latest_records(user)
    return [state_of(policy, latest.get(item)) for item, policy in POLICIES.items()]


def pending_items(user: User) -> list[str]:
    """다시 동의를 받아야 하는 필수 항목들. 표의 차례다."""
    return [state.item for state in consent_states(user) if state.pending]


def agree(user: User, item: str, version: int, now: datetime) -> None:
    """
    그 항목에 동의한다. 판이 오른 필수 항목에 다시 동의할 때도 이것이다.

    이미 그 판에 동의해 있으면 아무것도 적지 않는다. 표에 없으면 UnknownConsentItemError,
    지금의 판이 아니면 ConsentOutdatedError.
    """
    policy = policy_of(item)
    if version != policy.version:
        raise ConsentOutdatedError
    if state_of(policy, latest_records(user).get(item)).agreed_version == version:
        return
    ConsentRecord.objects.create(user=user, item=item, version=version, action=ConsentAction.AGREED, at=now)


def withdraw(user: User, item: str, now: datetime) -> None:
    """
    그 항목의 동의를 철회한다. 동의해 있지 않으면 아무것도 적지 않는다.

    표에 없으면 UnknownConsentItemError, 필수 항목이면 ConsentRequiredError.
    """
    policy = policy_of(item)
    if policy.required:
        raise ConsentRequiredError
    agreed_version = state_of(policy, latest_records(user).get(item)).agreed_version
    if agreed_version is None:
        return
    ConsentRecord.objects.create(user=user, item=item, version=agreed_version, action=ConsentAction.WITHDRAWN, at=now)


def erase_consents(user: User) -> None:
    """그 계정의 동의 기록을 모두 지운다. 만 14세 미만으로 막은 계정의 것이다. 그 나이의 동의는 쓸 수 없다."""
    ConsentRecord.objects.filter(user=user).delete()
