from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# MC numbers with deterministic mock outcomes for testing
_MOCK_NOT_FOUND = {"000000"}
_MOCK_NOT_AUTHORIZED = {"111111"}

# Realistic mock carrier pool — any MC not in the above sets returns one of these
_MOCK_CARRIERS = {
    "123456": {
        "dotNumber": 3456789,
        "legalName": "ACME TRUCKING LLC",
        "dbaName": "",
        "allowedToOperate": "Y",
        "commonAuthorityStatus": "AUTHORIZED",
        "contractAuthorityStatus": "AUTHORIZED",
        "brokerAuthorityStatus": "NOT AUTHORIZED",
        "totalPowerUnits": 12,
    },
    "654321": {
        "dotNumber": 9876543,
        "legalName": "SWIFT FREIGHT INC",
        "dbaName": "SWIFT FREIGHT",
        "allowedToOperate": "Y",
        "commonAuthorityStatus": "AUTHORIZED",
        "contractAuthorityStatus": "NOT AUTHORIZED",
        "brokerAuthorityStatus": "NOT AUTHORIZED",
        "totalPowerUnits": 45,
    },
    "789012": {
        "dotNumber": 1234567,
        "legalName": "BLUE RIDGE CARRIERS LLC",
        "dbaName": "",
        "allowedToOperate": "Y",
        "commonAuthorityStatus": "AUTHORIZED",
        "contractAuthorityStatus": "AUTHORIZED",
        "brokerAuthorityStatus": "NOT AUTHORIZED",
        "totalPowerUnits": 8,
    },
}

_MOCK_DEFAULT_CARRIER = {
    "dotNumber": 5550001,
    "legalName": "GENERIC TRANSPORT LLC",
    "dbaName": "",
    "allowedToOperate": "Y",
    "commonAuthorityStatus": "AUTHORIZED",
    "contractAuthorityStatus": "NOT AUTHORIZED",
    "brokerAuthorityStatus": "NOT AUTHORIZED",
    "totalPowerUnits": 3,
}


@dataclass
class CarrierInfo:
    eligible: bool
    mc_number: str
    carrier_name: Optional[str]
    dot_number: Optional[str]
    allowed_to_operate: Optional[str]
    reason: Optional[str]


def normalize_mc(raw: str) -> str:
    """Strip leading 'MC'/'mc', whitespace and dashes from a motor carrier number."""
    cleaned = raw.strip().upper()
    if cleaned.startswith("MC"):
        cleaned = cleaned[2:]
    return cleaned.replace("-", "").replace(" ", "")


def _carrier_from_payload(mc: str, carrier: dict) -> CarrierInfo:
    allowed = carrier.get("allowedToOperate", "")
    legal_name = carrier.get("legalName") or carrier.get("dbaName") or None
    dot = str(carrier.get("dotNumber", "")) or None

    if allowed != "Y":
        return CarrierInfo(
            eligible=False,
            mc_number=mc,
            carrier_name=legal_name,
            dot_number=dot,
            allowed_to_operate=allowed or "N",
            reason="Not authorized to operate",
        )

    return CarrierInfo(
        eligible=True,
        mc_number=mc,
        carrier_name=legal_name,
        dot_number=dot,
        allowed_to_operate="Y",
        reason=None,
    )


def _mock_lookup(mc: str) -> CarrierInfo:
    if mc in _MOCK_NOT_FOUND:
        return CarrierInfo(
            eligible=False,
            mc_number=mc,
            carrier_name=None,
            dot_number=None,
            allowed_to_operate=None,
            reason="MC number not found",
        )

    if mc in _MOCK_NOT_AUTHORIZED:
        return CarrierInfo(
            eligible=False,
            mc_number=mc,
            carrier_name="REVOKED CARRIER LLC",
            dot_number="0000001",
            allowed_to_operate="N",
            reason="Not authorized to operate",
        )

    carrier = _MOCK_CARRIERS.get(mc, _MOCK_DEFAULT_CARRIER)
    return _carrier_from_payload(mc, carrier)


async def lookup_carrier(mc_number: str) -> CarrierInfo:
    """Verify a carrier by MC/docket number against the FMCSA QC API.

    In mock mode (FMCSA_MOCK=true) no network call is made — useful for local
    dev and CI where the FMCSA endpoint is unreachable.
    """
    mc = normalize_mc(mc_number)

    if settings.FMCSA_MOCK:
        logger.debug("FMCSA mock lookup for MC %s", mc)
        return _mock_lookup(mc)

    url = f"{settings.FMCSA_BASE_URL}/docket-number/{mc}"
    params = {"webKey": settings.FMCSA_WEBKEY}

    try:
        async with httpx.AsyncClient(timeout=settings.FMCSA_TIMEOUT) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException:
        logger.warning("FMCSA request timed out for MC %s", mc)
        raise FMCSAError("FMCSA service timed out — please retry")
    except httpx.RequestError as exc:
        logger.error("FMCSA request error for MC %s: %s", mc, exc)
        raise FMCSAError("Could not reach FMCSA service")

    if response.status_code == 403:
        logger.error("FMCSA returned 403 — webKey may be invalid or IP not whitelisted")
        raise FMCSAError("FMCSA authentication failed — check FMCSA_WEBKEY")

    if response.status_code != 200:
        logger.error("FMCSA unexpected status %s for MC %s", response.status_code, mc)
        raise FMCSAError(f"FMCSA returned HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception:
        raise FMCSAError("FMCSA returned invalid JSON")

    content = data.get("content", [])

    # content is an array; empty means the MC was not found in the registry
    if not content:
        return CarrierInfo(
            eligible=False,
            mc_number=mc,
            carrier_name=None,
            dot_number=None,
            allowed_to_operate=None,
            reason="MC number not found",
        )

    carrier = content[0].get("carrier", {})
    return _carrier_from_payload(mc, carrier)


class FMCSAError(Exception):
    """Raised when the FMCSA service is unreachable or returns an unexpected response."""
