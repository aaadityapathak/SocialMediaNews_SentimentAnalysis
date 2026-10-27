"""
geographic filter for EventRecord and GkgRecord.
"""

from __future__ import annotations

from .gdelt_harvest import EventRecord, GkgRecord

AU_CAMEO = "AUS"
AU_FIPS = "AS"
VIC_ADM1 = "AS07"


def event_is_australia(record: EventRecord) -> bool:
    """
    Checks if an EventRecord features Australian affiliation.

    Parameters
    ----------
    record : EventRecord
        The parsed event.

    Returns
    -------
    bool
        True if action or actors geographically associate with Australia.
    """
    return (
        record.ActionGeo_CountryCode == AU_FIPS
        or record.Actor1Geo_CountryCode == AU_FIPS
        or record.Actor2Geo_CountryCode == AU_FIPS
        or record.Actor1CountryCode == AU_CAMEO
        or record.Actor2CountryCode == AU_CAMEO
    )


def event_is_victoria(record: EventRecord) -> bool:
    """
    Checks if an EventRecord explicitly links to Victoria, Australia.

    Parameters
    ----------
    record : EventRecord
        The parsed event.

    Returns
    -------
    bool
        True if the event or any actor specifies the Victoria ADM1 code.
    """
    return (
        record.ActionGeo_ADM1Code == VIC_ADM1
        or record.Actor1Geo_ADM1Code == VIC_ADM1
        or record.Actor2Geo_ADM1Code == VIC_ADM1
    )


def event_matches(
    record: EventRecord,
    country_fips: str | None = None,
    adm1_code: str | None = None,
    actor_cameo: str | None = None,
) -> bool:
    """
    Evaluates an EventRecord against region attributes.

    Parameters
    ----------
    record : EventRecord
    country_fips : str | None, optional
    adm1_code : str | None, optional - region code.
    actor_cameo : str | None, optional

    Returns
    -------
    bool
        True if all provided criteria map correctly; False otherwise.
    """
    if country_fips and not (
        record.ActionGeo_CountryCode == country_fips
        or record.Actor1Geo_CountryCode == country_fips
        or record.Actor2Geo_CountryCode == country_fips
    ):
        return False

    if adm1_code and not (
        record.ActionGeo_ADM1Code == adm1_code
        or record.Actor1Geo_ADM1Code == adm1_code
        or record.Actor2Geo_ADM1Code == adm1_code
    ):
        return False

    return not actor_cameo or (
        record.Actor1CountryCode == actor_cameo
        or record.Actor2CountryCode == actor_cameo
    )


def gkg_is_australia(record: GkgRecord) -> bool:
    """
    Checks if a GKG record contains Australian locational entities.

    Parameters
    ----------
    record : GkgRecord
        The parsed knowledge graph item.

    Returns
    -------
    bool
        True if Australia is found in any location block.
    """
    for block in record.location_blocks():
        if len(block) > 2 and block[2] == AU_FIPS:
            return True
    return False


def gkg_is_victoria(record: GkgRecord) -> bool:
    """
    Checks if a GKG record contains Victorian locational entities.

    Parameters
    ----------
    record : GkgRecord
        The parsed knowledge graph item.

    Returns
    -------
    bool
        True if Victoria is found in any location block.
    """
    for block in record.location_blocks():
        if len(block) > 3 and block[3] == VIC_ADM1:
            return True
    return False


def gkg_matches(
    record: GkgRecord,
    country_fips: str | None = None,
    adm1_code: str | None = None,
) -> bool:
    """
    Evaluates a GkgRecord against arbitrary region attributes.

    Parameters
    ----------
    record : GkgRecord
        The parsed knowledge graph item.
    country_fips : str | None, optional
        Target FIPS location code.
    adm1_code : str | None, optional
        Target ADM1 region code.

    Returns
    -------
    bool
        True if any location block satisfies the constraints; False otherwise.
    """
    if not country_fips and not adm1_code:
        return True
    return any(
        (not country_fips or (len(block) > 2 and block[2] == country_fips))
        and (not adm1_code or (len(block) > 3 and block[3] == adm1_code))
        for block in record.location_blocks()
    )
