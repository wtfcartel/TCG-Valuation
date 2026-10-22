"""Geography classification relative to a Melbourne (Ormond) home base. Deterministic.

National titles are not assumed to be Melbourne-workable: a role counts as Melbourne-workable only
when the advertisement places it in Victoria, lists Melbourne among its locations, or says it is
remote / location-flexible within Australia.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from logidx.enums import Geography, WorkMode

MELBOURNE_PLACES = [
    "melbourne",
    "melbourne cbd",
    "ormond",
    "docklands",
    "southbank",
    "south melbourne",
    "port melbourne",
    "west melbourne",
    "north melbourne",
    "east melbourne",
    "st kilda",
    "richmond",
    "cremorne",
    "collingwood",
    "fitzroy",
    "carlton",
    "hawthorn",
    "camberwell",
    "box hill",
    "doncaster",
    "ringwood",
    "bayswater",
    "knoxfield",
    "scoresby",
    "rowville",
    "wantirna",
    "mulgrave",
    "clayton",
    "notting hill",
    "oakleigh",
    "moorabbin",
    "cheltenham",
    "mentone",
    "braeside",
    "keysborough",
    "dandenong",
    "dandenong south",
    "hallam",
    "lyndhurst",
    "carrum downs",
    "frankston",
    "seaford",
    "brighton",
    "bentleigh",
    "caulfield",
    "glen waverley",
    "burwood",
    "malvern",
    "prahran",
    "south yarra",
    "toorak",
    "kew",
    "heidelberg",
    "bundoora",
    "preston",
    "thomastown",
    "epping",
    "somerton",
    "campbellfield",
    "coolaroo",
    "broadmeadows",
    "tullamarine",
    "melbourne airport",
    "essendon",
    "essendon fields",
    "keilor park",
    "airport west",
    "sunshine",
    "sunshine west",
    "derrimut",
    "truganina",
    "laverton",
    "laverton north",
    "altona",
    "altona north",
    "brooklyn",
    "footscray",
    "west footscray",
    "yarraville",
    "spotswood",
    "williamstown",
    "ravenhall",
    "deer park",
    "hoppers crossing",
    "werribee",
    "tarneit",
    "point cook",
    "craigieburn",
    "mickleham",
    "pakenham",
    "officer",
    "cranbourne",
    "berwick",
    "narre warren",
    "lilydale",
    "chirnside park",
]
REGIONAL_VIC = [
    "geelong",
    "ballarat",
    "bendigo",
    "shepparton",
    "mildura",
    "wodonga",
    "traralgon",
    "morwell",
    "warrnambool",
    "latrobe valley",
    "horsham",
    "sale",
    "bairnsdale",
    "wangaratta",
    "echuca",
    "portland",
    "hamilton",
    "swan hill",
    "colac",
    "warragul",
]
INTERSTATE_CAPITALS = {
    "sydney": "NSW",
    "parramatta": "NSW",
    "newcastle": "NSW",
    "wollongong": "NSW",
    "brisbane": "QLD",
    "gold coast": "QLD",
    "sunshine coast": "QLD",
    "townsville": "QLD",
    "cairns": "QLD",
    "adelaide": "SA",
    "perth": "WA",
    "fremantle": "WA",
    "hobart": "TAS",
    "launceston": "TAS",
    "darwin": "NT",
    "canberra": "ACT",
    "ingleburn": "NSW",
    "eastern creek": "NSW",
    "wetherill park": "NSW",
    "moorebank": "NSW",
    "botany": "NSW",
    "mascot": "NSW",
    "north ryde": "NSW",
    "macquarie park": "NSW",
    "eagle farm": "QLD",
    "acacia ridge": "QLD",
    "port of brisbane": "QLD",
}
STATES = {
    "nsw": "NSW",
    "new south wales": "NSW",
    "qld": "QLD",
    "queensland": "QLD",
    "sa": "SA",
    "south australia": "SA",
    "wa": "WA",
    "western australia": "WA",
    "tas": "TAS",
    "tasmania": "TAS",
    "nt": "NT",
    "northern territory": "NT",
    "act": "ACT",
    "australian capital territory": "ACT",
}
VIC_TOKENS = ["vic", "victoria"]
OVERSEAS = [
    "new zealand",
    "auckland",
    "wellington",
    "singapore",
    "united kingdom",
    "london",
    "united states",
    "usa",
    "hong kong",
    "dubai",
    "india",
    "philippines",
    "manila",
    "malaysia",
    "kuala lumpur",
    "germany",
    "netherlands",
    "amsterdam",
    "canada",
    "toronto",
]

_FLEX = re.compile(
    r"(location\s+(is\s+)?(flexible|negotiable)|flexible\s+on\s+location|any\s+(major\s+|australian\s+)?"
    r"(capital\s+)?cit(y|ies)|(based|located)\s+in\s+any|work\s+from\s+anywhere\s+in\s+australia|"
    r"(sydney|brisbane|adelaide|perth)\s+(or|/)\s+melbourne|melbourne\s+(or|/)\s+(sydney|brisbane|adelaide|perth)|"
    r"(fully\s+)?remote\s+(within|across|in)\s+australia|anywhere\s+in\s+australia)",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"\b(fully\s+remote|100%\s+remote|remote[\s-]first|work\s+from\s+home|wfh|remote)\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b|flexible\s+working|split\s+between\s+(home|office)", re.IGNORECASE)
_ONSITE = re.compile(
    r"\b(on[\s-]?site|office[\s-]based|site[\s-]based|in\s+the\s+office\s+\d|5\s+days\s+in)\b", re.IGNORECASE
)
_TRAVEL = re.compile(
    r"([^.\n]{0,80}\b(interstate\s+travel|travel\s+(interstate|nationally|across\s+\w+|up\s+to\s+\d+%|"
    r"required|regularly)|significant\s+travel|extensive\s+travel|frequent\s+travel|relocat\w+|"
    r"fly[\s-]in[\s-]fly[\s-]out|fifo)\b[^.\n]{0,80})",
    re.IGNORECASE,
)
_PLACE_CACHE: dict[str, re.Pattern[str]] = {}


def _has(text: str, place: str) -> bool:
    rx = _PLACE_CACHE.get(place)
    if rx is None:
        rx = re.compile(rf"(?<![a-z]){re.escape(place)}(?![a-z])", re.IGNORECASE)
        _PLACE_CACHE[place] = rx
    return bool(rx.search(text))


@dataclass
class GeoResult:
    geography: Geography
    reason: str
    work_mode: WorkMode
    work_base: str | None
    travel: str | None


def _states_in(text: str) -> set[str]:
    found = {code for name, code in STATES.items() if _has(text, name)}
    found |= {code for city, code in INTERSTATE_CAPITALS.items() if _has(text, city)}
    return found


def classify_location(location: str | None, description: str = "", title: str = "") -> GeoResult:
    loc = (location or "").strip()
    desc = description or ""
    mode = WorkMode.UNKNOWN
    combined = f"{loc}\n{desc}"
    if _REMOTE.search(loc) or re.search(r"\bfully\s+remote|100%\s+remote|remote[\s-]first", desc, re.I):
        mode = WorkMode.REMOTE
    elif _HYBRID.search(combined):
        mode = WorkMode.HYBRID
    elif _ONSITE.search(combined):
        mode = WorkMode.ONSITE
    travel_hits = [m.group(1).strip() for m in _TRAVEL.finditer(desc)][:3]
    travel = " … ".join(travel_hits) or None

    loc_melb = any(_has(loc, p) for p in MELBOURNE_PLACES) or any(_has(loc, v) for v in VIC_TOKENS)
    loc_regional = any(_has(loc, p) for p in REGIONAL_VIC)
    loc_states = _states_in(loc)
    loc_overseas = [p for p in OVERSEAS if _has(loc, p)]
    flexible = bool(_FLEX.search(combined))
    desc_mentions_melb = _has(desc, "melbourne")

    def result(geo: Geography, reason: str) -> GeoResult:
        return GeoResult(geo, reason, mode, loc or None, travel)

    if loc_overseas and not (loc_melb or loc_states):
        return result(Geography.OVERSEAS, f"location names {loc_overseas[0]}")
    if loc_melb and not loc_states:
        if loc_regional and not any(_has(loc, p) for p in MELBOURNE_PLACES):
            return result(Geography.REGIONAL_VIC, "regional Victoria — check commute and attendance")
        return result(Geography.MELBOURNE, "location is in Melbourne / Victoria")
    if loc_regional and not loc_states:
        return result(Geography.REGIONAL_VIC, "regional Victoria — check commute and attendance")
    if loc_melb and loc_states:
        return result(Geography.NATIONAL_MELBOURNE_OK, "Melbourne is one of the listed locations")
    if mode == WorkMode.REMOTE and not loc_states:
        return result(Geography.REMOTE_AU, "advertised as remote")
    if loc_states:
        if flexible or (
            desc_mentions_melb and re.search(r"melbourne[^.\n]{0,40}(based|considered|option)", desc, re.I)
        ):
            return result(
                Geography.NATIONAL_MELBOURNE_OK,
                f"listed in {', '.join(sorted(loc_states))}, but the ad states location flexibility",
            )
        return result(Geography.INTERSTATE, f"based in {', '.join(sorted(loc_states))}; no Melbourne option stated")
    if re.search(r"\b(australia|national|nationwide|anz)\b", loc, re.I) or not loc:
        if flexible:
            return result(Geography.NATIONAL_MELBOURNE_OK, "location flexible within Australia")
        if desc_mentions_melb and not _states_in(desc):
            return result(Geography.MELBOURNE, "description places the role in Melbourne")
        if not loc:
            return result(Geography.UNKNOWN, "no location given")
        return result(
            Geography.NATIONAL_UNCONFIRMED, "national or Australia-wide listing; required work base not stated"
        )
    return result(Geography.UNKNOWN, f"location '{loc}' not recognised")
