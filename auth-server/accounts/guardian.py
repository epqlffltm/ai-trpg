# auth-server/accounts/guardian.py

"""
보호자 동의(#336). 미성년자(만 19세 미만)는 보호자가 동의해야 결제할 수 있다. 결제를 막는 것은 결제 서버다(#337).

  1. 요청: 본인인증을 마친 미성년자가 보호자의 이메일을 적는다. 그 주소로 동의 링크가 간다(7일)
  2. 동의: 보호자가 링크에서 휴대폰 본인인증을 하고 동의한다. 보호자는 성년이어야 하고 미성년자 본인이 아니어야 한다
  3. 철회: 보호자가 메일의 철회 링크를 연다. 미성년자는 철회하지 못한다

보호자는 한 명이다. 동의한 동안에는 미성년자가 보호자를 바꾸지 못한다. 바꾸게 하면 아무 성인에게 다시 동의를 받아
보호자의 철회를 피할 수 있다. 철회된 뒤에는 다시 요청할 수 있다.
동의와 철회는 결제 서버에 알릴 결제 자격을 바꾼다. 같은 트랜잭션에서 적는다(payment_eligibility.py).

보호자의 관계(부모인지)는 확인하지 않는다. 서류를 받지 않기로 했다.
남는 것은 동의한 사람의 본인인증 기록(사람 열쇠)이다.
"""

import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.age import has_reached, korean_today, legal_adult_from
from accounts.guardian_links import (
    InvalidGuardianLinkError,
    issue_consent_token,
    issue_revoke_token,
    read_consent_token,
    read_revoke_token,
)
from accounts.identity import person_key
from accounts.identity_providers import IdentityResult, get_identity_provider
from accounts.mail import (
    send_guardian_consent_request,
    send_guardian_consented_notice,
    send_guardian_revoked_notice,
    send_minor_guardian_notice,
)
from accounts.models import GuardianConsent, GuardianConsentStatus, IdentityVerification, User
from accounts.payment_eligibility import mark_changed

# 요청 메일의 발송 제한. 미성년자가 남의 메일함에 링크를 퍼붓지 못하게 한다.
# 다시 보내기까지의 대기와, 하루에 보낼 수 있는 수다. 주소를 잘못 적어 다시 보내는 정도는 넉넉히 된다
REQUEST_COOLDOWN = timedelta(minutes=1)
REQUEST_WINDOW = timedelta(hours=24)
MAX_REQUESTS_PER_WINDOW = 5

# 상태가 없는 계정의 이름. 내 정보의 guardian_consent 에 실린다
NO_CONSENT = 'none'


class IdentityRequiredError(Exception):
    """본인인증을 하지 않아 나이를 모른다."""


class GuardianNotNeededError(Exception):
    """이미 성년이다. 보호자의 동의가 필요 없다."""


class GuardianConsentActiveError(Exception):
    """이미 보호자가 동의했다. 보호자가 철회하기 전에는 바꿀 수 없다."""


class GuardianEmailIsOwnError(Exception):
    """보호자의 이메일로 자기 이메일을 적었다."""


@dataclass
class GuardianRequestUnavailableError(Exception):
    """요청 메일을 지금은 보낼 수 없다. retry_after 뒤에 다시 할 수 있다."""

    retry_after: timedelta


class GuardianNotAdultError(Exception):
    """동의하려는 보호자가 성년이 아니다."""


class GuardianIsMinorError(Exception):
    """동의하려는 보호자가 미성년자 본인이다."""


def guardian_status_of(user: User) -> str:
    """그 계정의 보호자 동의 상태. requested, consented, revoked 중 하나이고, 요청한 적이 없으면 none 이다."""
    consent = GuardianConsent.objects.filter(minor=user).first()
    return consent.status if consent else NO_CONSENT


@transaction.atomic
def request_guardian_consent(*, minor: User, guardian_email: str) -> GuardianConsent:
    """
    보호자에게 동의 링크를 보낸다. 앞서 보낸 링크가 있으면 그것은 쓸 수 없게 된다.

    본인인증 전이면 IdentityRequiredError, 이미 성년이면 GuardianNotNeededError, 보호자가 이미 동의했으면
    GuardianConsentActiveError, 자기 이메일이면 GuardianEmailIsOwnError,
    너무 자주 보냈으면 GuardianRequestUnavailableError.
    """
    _ensure_minor(minor)
    if guardian_email.strip().lower() == minor.email.lower():
        raise GuardianEmailIsOwnError
    now = timezone.now()
    consent = _lock_or_create(minor, now)
    if consent.status == GuardianConsentStatus.CONSENTED:
        raise GuardianConsentActiveError
    _count_request(consent, now)
    _restart(consent, guardian_email.strip(), now)
    send_guardian_consent_request(
        minor=minor,
        guardian_email=consent.guardian_email,
        token=issue_consent_token(minor_public_id=minor.public_id, nonce=consent.link_nonce),
    )
    return consent


def give_guardian_consent(*, consent_token: str, identity_token: str) -> GuardianConsent:
    """
    보호자가 동의한다. 링크를 확인하고, 보호자의 본인인증을 하고, 동의를 적는다.

    링크를 쓸 수 없으면 InvalidGuardianLinkError, 미성년자가 그새 성년이 되었으면 GuardianNotNeededError,
    본인확인 업체의 오류(IdentityTokenError, IdentityUnavailableError), 보호자가 성년이 아니면 GuardianNotAdultError,
    미성년자 본인이면 GuardianIsMinorError.
    업체에는 트랜잭션 밖에서 묻는다. 링크는 묻기 전에 한 번, 적기 전에 잠그고 한 번 더 확인한다.
    """
    link = read_consent_token(consent_token)
    _find_requested(link.minor_public_id, link.nonce)
    guardian = get_identity_provider().verify(identity_token)
    return _record_consent(link.minor_public_id, link.nonce, guardian)


def revoke_guardian_consent(*, revoke_token: str) -> bool:
    """
    보호자가 동의를 철회한다. 이번에 철회했으면 True, 이미 철회되어 있었으면 False 다.

    링크를 쓸 수 없으면 InvalidGuardianLinkError. 같은 링크를 두 번 열어도 된다.
    """
    link = read_revoke_token(revoke_token)
    with transaction.atomic():
        consent = _lock_by_link(link.minor_public_id, link.nonce)
        if consent.status == GuardianConsentStatus.REVOKED:
            return False
        if consent.status != GuardianConsentStatus.CONSENTED:
            raise InvalidGuardianLinkError
        guardian_email = consent.guardian_email
        consent.status = GuardianConsentStatus.REVOKED
        consent.revoked_at = timezone.now()
        # 더 보낼 일이 없다. 다툼에는 동의한 사람의 열쇠와 시각이 남는다
        consent.guardian_email = ''
        consent.save(update_fields=['status', 'revoked_at', 'guardian_email'])
        mark_changed(consent.minor)
        send_guardian_revoked_notice(minor=consent.minor, guardian_email=guardian_email)
        send_minor_guardian_notice(minor=consent.minor, consented=False)
    return True


def _ensure_minor(minor: User) -> None:
    """본인인증을 했고 아직 성년이 아닌지 본다."""
    verification = IdentityVerification.objects.filter(user=minor).first()
    if verification is None:
        raise IdentityRequiredError
    if has_reached(verification.legal_adult_from, korean_today()):
        raise GuardianNotNeededError


def _lock_or_create(minor: User, now) -> GuardianConsent:
    """그 미성년자의 동의 줄을 잠근다. 없으면 만든다. 같은 미성년자의 요청 둘이 함께 와도 차례로 지나간다."""
    consent, _ = GuardianConsent.objects.select_for_update().get_or_create(
        minor=minor,
        defaults={
            'status': GuardianConsentStatus.REQUESTED,
            'link_nonce': '',
            'requested_at': now,
            'window_started_at': now,
        },
    )
    return consent


def _count_request(consent: GuardianConsent, now) -> None:
    """요청 메일 하나를 센다. 대기가 안 지났거나 하루의 수를 넘으면 GuardianRequestUnavailableError."""
    if consent.requests_in_window and now < consent.requested_at + REQUEST_COOLDOWN:
        raise GuardianRequestUnavailableError(retry_after=consent.requested_at + REQUEST_COOLDOWN - now)
    if now >= consent.window_started_at + REQUEST_WINDOW:
        consent.window_started_at = now
        consent.requests_in_window = 0
    if consent.requests_in_window >= MAX_REQUESTS_PER_WINDOW:
        raise GuardianRequestUnavailableError(retry_after=consent.window_started_at + REQUEST_WINDOW - now)
    consent.requests_in_window += 1


def _restart(consent: GuardianConsent, guardian_email: str, now) -> None:
    """새 요청으로 줄을 처음부터 다시 쓴다. 일회 값을 바꿔 앞서 보낸 링크를 쓸 수 없게 한다."""
    consent.guardian_email = guardian_email
    consent.status = GuardianConsentStatus.REQUESTED
    consent.link_nonce = secrets.token_hex(16)
    consent.guardian_person_key = ''
    consent.requested_at = now
    consent.consented_at = None
    consent.revoked_at = None
    consent.save()


def _find_requested(minor_public_id, nonce: str) -> GuardianConsent:
    """링크가 가리키는, 동의를 기다리는 줄. 없거나 미성년자를 쓸 수 없으면 InvalidGuardianLinkError."""
    consent = (
        GuardianConsent.objects.select_related('minor')
        .filter(minor__public_id=minor_public_id, link_nonce=nonce, status=GuardianConsentStatus.REQUESTED)
        .first()
    )
    return _usable(consent)


def _lock_by_link(minor_public_id, nonce: str) -> GuardianConsent:
    """링크가 가리키는 줄을 잠근다. 없으면 InvalidGuardianLinkError."""
    consent = (
        GuardianConsent.objects.select_for_update()
        .select_related('minor')
        .filter(minor__public_id=minor_public_id, link_nonce=nonce)
        .first()
    )
    if consent is None:
        raise InvalidGuardianLinkError
    return consent


def _usable(consent: GuardianConsent | None) -> GuardianConsent:
    """동의를 받을 수 있는 줄인지 본다. 막힌 계정이면 링크를 쓸 수 없고, 그새 성년이 되었으면 필요 없다."""
    if consent is None or not consent.minor.is_active:
        raise InvalidGuardianLinkError
    _ensure_minor(consent.minor)
    return consent


@transaction.atomic
def _record_consent(minor_public_id, nonce: str, guardian: IdentityResult) -> GuardianConsent:
    """잠그고 다시 확인한 뒤 동의를 적는다. 결제 자격과 알림 메일도 같은 트랜잭션이다."""
    consent = _lock_by_link(minor_public_id, nonce)
    if consent.status != GuardianConsentStatus.REQUESTED:
        raise InvalidGuardianLinkError
    _usable(consent)
    _ensure_guardian(consent.minor, guardian)
    consent.status = GuardianConsentStatus.CONSENTED
    consent.guardian_person_key = person_key(guardian.di)
    consent.consented_at = timezone.now()
    consent.save(update_fields=['status', 'guardian_person_key', 'consented_at'])
    mark_changed(consent.minor)
    send_guardian_consented_notice(
        minor=consent.minor,
        guardian_email=consent.guardian_email,
        revoke_token=issue_revoke_token(minor_public_id=minor_public_id, nonce=nonce),
    )
    send_minor_guardian_notice(minor=consent.minor, consented=True)
    return consent


def _ensure_guardian(minor: User, guardian: IdentityResult) -> None:
    """보호자가 성년이고 미성년자 본인이 아닌지 본다."""
    if not has_reached(legal_adult_from(guardian.birth_date), korean_today()):
        raise GuardianNotAdultError
    if IdentityVerification.objects.filter(user=minor, person_key=person_key(guardian.di)).exists():
        raise GuardianIsMinorError
