#!/usr/bin/env python3
"""Scrape NM SoS election results (electionresults.sos.nm.gov) into OpenElections CSVs.

The SoS site is an ASP.NET WebForms app backed by a public WCF JSON API
(electionresults-api.sos.nm.gov/NMResultsAjax.svc). There is no API to list
races, so races are enumerated by scraping the resultsSW.aspx category pages
(FED, SW, LGX, ... and per-county CTYSPEC pages) and parsing the
`export-button` attributes (raceid/party/officeseqno/countyid) on each race
box. Results are then fetched per race from the JSON API at county level
(category=CTY) and precinct level (category=PREC), and written as two CSVs:
county first, then precinct.

Examples:
    # 2024 general (archive)
    uv run parsers/sos_results.py --eid 2882 --election-type General \
        --date 2024-11-05 --outdir 2024

    # 2026 primary (live election on the site)
    uv run parsers/sos_results.py --live --election-type Primary \
        --date 2026-06-02 --outdir 2026

    # enumerate races without fetching results
    uv run parsers/sos_results.py --eid 2882 --election-type General \
        --date 2024-11-05 --dry-run --categories FED,SW

    # generate and diff against an existing OpenElections precinct file
    uv run parsers/sos_results.py --eid 2882 ... --compare 2024/20241105__nm__general__precinct.csv
"""

import argparse
import csv
import datetime
import hashlib
import html as html_lib
import io
import json
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import requests

SITE = "https://electionresults.sos.nm.gov/"
API = "https://electionresults-api.sos.nm.gov/NMResultsAjax.svc/"

# Page-level contest categories on resultsSW.aspx. County offices live on
# per-county CTYSPEC pages reached via resultsList.aspx; both CTYSPEC and
# CTYALL map to API type "CTY".
PAGE_TYPES = ["FED", "SW", "LGX", "JDX", "DAX", "ECX", "JMC", "MGX",
              "CLX", "HDX", "SWX", "MUX"]
# If a race in one of these categories returns no data, treat it as a real
# failure (exit non-zero). Empty county/municipal races are tolerated.
FAIL_EMPTY_TYPES = {"FED", "SW", "LGX", "JDX"}

COUNTIES = ['Bernalillo', 'Catron', 'Chaves', 'Cibola', 'Colfax', 'Curry',
            'De Baca', 'Dona Ana', 'Eddy', 'Grant', 'Guadalupe', 'Harding',
            'Hidalgo', 'Lea', 'Lincoln', 'Los Alamos', 'Luna', 'McKinley',
            'Mora', 'Otero', 'Quay', 'Rio Arriba', 'Roosevelt', 'San Juan',
            'San Miguel', 'Sandoval', 'Santa Fe', 'Sierra', 'Socorro', 'Taos',
            'Torrance', 'Union', 'Valencia']

ORDINALS = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5,
            "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9, "TENTH": 10,
            "ELEVENTH": 11, "TWELFTH": 12, "THIRTEENTH": 13}
# so page headings like "District Attorney 10TH JUDICIAL DISTRICT" parse too
ORDINALS.update({f"{n}TH": n for n in range(4, 14)})
ORDINALS.update({"1ST": 1, "2ND": 2, "3RD": 3})

# GetCandidates returns long-form party names; map to the repo's 3-letter codes.
PARTY_CODES = {"Democrat": "DEM", "Republican": "REP", "Libertarian": "LIB",
               "Green": "GRE", "Independent": "IND", "Constitution": "CON",
               "Independent American": "IND", "Write-In": "",
               "Nonpartisan": "NA", "": ""}

# Precinct rows to drop from precinct CSVs (per-county totals etc.).
DROP_PRECINCT_RE = re.compile(r"^(TOTALS?|COUNTYWIDE)$", re.I)

# Exact office-name matches (applied to the page <h1> race title after
# stripping a trailing " - <County>" suffix; case-insensitive, output uses
# the repo's established casing). Empty district for statewide offices.
OFFICE_EXACT = {
    "president and vice president of the united states": ("President", ""),
    "united states senator": ("U.S. Senate", ""),
    "governor": ("Governor", ""),
    "lieutenant governor": ("Lieutenant Governor", ""),
    "secretary of state": ("Secretary Of State", ""),
    "state auditor": ("State Auditor", ""),
    "state treasurer": ("State Treasurer", ""),
    "attorney general": ("Attorney General", ""),
    "commissioner of public lands": ("Commissioner Of Public Lands", ""),
    "municipal judge": ("Municipal Judge", ""),
    "county clerk": ("County Clerk", ""),
    "county treasurer": ("County Treasurer", ""),
    "county sheriff": ("County Sheriff", ""),
    "county assessor": ("County Assessor", ""),
    "probate judge": ("Probate Judge", ""),
    "county commissioner at large": ("County Commissioner At Large", ""),
    # 2022 general form: the joint ticket keeps the full candidate names
    # (matches the hand-built 2018 file's office="Governor" rows)
    "governor and lieutenant governor": ("Governor", ""),
}

OFFICE_PATTERNS = [
    (re.compile(r"^united states representative\b.*\bdistrict (\d+)\s*$", re.I),
     lambda m: ("U.S. House", str(int(m.group(1))))),
    (re.compile(r"^state senator\b.*\bdistrict (\d+)\s*$", re.I),
     lambda m: ("State Senate", str(int(m.group(1))))),
    (re.compile(r"^state representative\b.*\bdistrict (\d+)\s*$", re.I),
     lambda m: ("State House", str(int(m.group(1))))),
    (re.compile(r"^public education commissioner\b.*\bdistrict (\d+)\s*$", re.I),
     lambda m: ("Public Education Commissioner", str(int(m.group(1))))),
    (re.compile(r"^county commissioner by commissioner district\b.*\b(?:district|dist\.?)\s*(\d+)\s*$", re.I),
     lambda m: ("County Commissioner", str(int(m.group(1))))),
    (re.compile(r"^district attorney\s+([a-z0-9]+)\s+judicial district\s*$", re.I),
     lambda m: ("District Attorney", str(ORDINALS.get(m.group(1).upper(), m.group(1))))),
    (re.compile(r"^district attorney\s+([a-z0-9]+)\s+judicial district\s*:\s*division\s*(\d+)\s*$", re.I),
     lambda m: ("District Attorney - Division %d" % int(m.group(2)),
                str(ORDINALS.get(m.group(1).upper(), m.group(1))))),
    (re.compile(r"^district court judge\s+([a-z0-9]+)\s+judicial district\s*:\s*division\s*(\d+)\s*$", re.I),
     lambda m: ("District Court Judge - Division %d" % int(m.group(2)),
                str(ORDINALS.get(m.group(1).upper(), m.group(1))))),
    (re.compile(r"^judge of the court of appeals\s+position\s*(\d+)\s*$", re.I),
     lambda m: ("Judge of the Court of Appeals - Position %d" % int(m.group(1)), "")),
    (re.compile(r"^judge of the metropolitan court\b.*\bdivision\s*(\d+)\s*$", re.I),
     lambda m: ("Judge of the Metropolitan Court - Division %d" % int(m.group(1)), "")),
    (re.compile(r"^magistrate judge\b.*\bdivision\s*(\d+)\s*$", re.I),
     lambda m: ("Magistrate Judge - Division %d" % int(m.group(1)), "")),
    # 2026 primary forms: magistrate districts are numbered per county court
    # (De Baca is "MAGISTRATE DISTRICT 10"), and many small counties elect
    # at large with no division at all ("... MAGISTRATE", "... MAGISTRATE- MORA").
    (re.compile(r"^magistrate judge\b.*\bmagistrate district\s+(\d+)\s*$", re.I),
     lambda m: ("Magistrate Judge", str(int(m.group(1))))),
    (re.compile(r"^magistrate judge\b.*\bmagistrate(?:\s*-\s*\w+)?\s*$", re.I),
     lambda m: ("Magistrate Judge", "")),
    # 2022 primary form: at-large commissioner seats are numbered by position
    (re.compile(r"^county commissioner at large\b.*\bposition\s*(\d+)\s*$", re.I),
     lambda m: ("County Commissioner At Large", str(int(m.group(1))))),
    (re.compile(r"^municipal judge\b.*\bmunicipal district\s+(\d+)\s*$", re.I),
     lambda m: ("Municipal Judge", str(int(m.group(1))))),
    # 2022 primary: supreme court seats are numbered by position (mirrors the
    # Court of Appeals convention); the unnumbered title passes through verbatim
    (re.compile(r"^justice of the supreme court\s*position\s*(\d+)\s*$", re.I),
     lambda m: ("Justice of the Supreme Court - Position %d" % int(m.group(1)), "")),
]

# Ballot questions with a standard short prefix keep the short form as the
# office (matches the existing 2024 file: "Constitutional Amendment 1").
QUESTION_SHORT = re.compile(r"^(constitutional amendment\s+\d+|bond question\s+\d+)\b", re.I)

# Races whose JSON response comes back empty while the page shows totals
# (known for 2024-archive county commissioner races) fall back to the page's
# own candidate totals for the county CSV, and to the page's XLSX export
# (a WebForms postback) for precinct rows.


@dataclass
class Race:
    raceid: int
    osn: int
    party: str            # "" for general races; DEM/REP for primary ballots
    countyid: str         # "01 " (trailing space) for county races; "" otherwise
    page_type: str        # FED/SW/LGX/... or "CTY" for per-county races
    title: str            # page <h1> race heading (carries district info)
    search_id: str = ""   # SearchResults.aspx contest id (from the box share links)
    page_params: dict = field(default_factory=dict)   # URL params of the page the race was found on
    county_name: str = ""                          # for CTY races: county of the race
    page_candidates: list = field(default_factory=list)  # [(name, votes)] shown in the page race box


def log(msg):
    print(msg, file=sys.stderr)


def _attrs(tag):
    """Extract an attribute dict from a single HTML tag string."""
    return dict(re.findall(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)="([^"]*)"', tag))


def strip_tags(s):
    # collapse whitespace: page markup leaves newlines and double spaces
    # inside race headings ("City of  Alamogordo"), which would otherwise
    # land verbatim in the office column and trip the file-format tests
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def strip_county_suffix(title):
    """Strip a trailing ' - <CountyName>' suffix from a race heading."""
    for c in COUNTIES:
        suffix = " - " + c
        if title.lower().endswith(suffix.lower()):
            return title[:-len(suffix)].strip()
    return title.strip()


def map_office(title):
    """Map a page race heading to (office, district).

    Returns (office, district, mapped). Unmapped headings come back verbatim
    (trailing county suffix stripped) with an empty district and mapped=False
    so they can be logged loudly; nothing is ever silently dropped.
    """
    cleaned = re.sub(r"\s+", " ", strip_county_suffix(title.strip())).strip()
    key = re.sub(r"\s+", " ", cleaned).lower()
    key = key.rstrip(" :")
    m = QUESTION_SHORT.match(cleaned)
    if m:
        short = re.sub(r"\s+", " ", m.group(0)).strip()
        return title_case_office(short), "", True
    # Judicial retention questions: office is the full heading (Yes/No rows).
    if re.match(r"^JUDICIAL RETENTION:\s+Shall\b", cleaned, re.I):
        return cleaned, "", True
    # Ballot questions (bonds, levies, district formations, ...): the office
    # is the full heading verbatim; candidate rows are Yes/No with party NA.
    if (re.search(r"\bSHALL\b", cleaned, re.I) or re.search(r"\bQUESTION\b", cleaned, re.I)
            or cleaned.endswith("?")):
        return cleaned, "", True
    if key in OFFICE_EXACT:
        return OFFICE_EXACT[key][0], OFFICE_EXACT[key][1], True
    for pattern, fn in OFFICE_PATTERNS:
        m = pattern.match(cleaned)
        if m:
            office, district = fn(m)
            return office, district, True
    # Generic fallback: a trailing "DISTRICT N" moves to the district column.
    m = re.search(r"\s+DISTRICT\s+(\d+)\s*$", cleaned, re.I)
    if m:
        return cleaned[:m.start()].strip(), str(int(m.group(1))), False
    return cleaned, "", False


def title_case_office(s):
    """Title-case an office name without touching 'U.S.'-style tokens."""
    words = []
    for i, w in enumerate(s.split()):
        if w.isupper() or "." in w:
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


class Fetcher:
    """HTTP fetcher with retries, throttling, and a sha1-keyed disk cache."""

    def __init__(self, cache_dir, sleep_s, refresh=False):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.sleep_s = sleep_s
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "openelections-data-nm scraper "
            "(github.com/openelections/openelections-data-nm)")

    def _cache_path(self, url, params, ext):
        qs = urlencode(sorted((params or {}).items()))
        key = hashlib.sha1((url + "?" + qs).encode("utf-8")).hexdigest()
        return self.cache / (key + ext)

    def get(self, url, params=None, fresh=False):
        """GET returning text (aspx pages). Cached unless fresh=True."""
        path = self._cache_path(url, params, ".html")
        if not fresh and not self.refresh and path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        last_err = None
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=60)
                r.raise_for_status()
                text = r.text
                path.write_text(text, encoding="utf-8")
                time.sleep(self.sleep_s)
                return text
            except requests.RequestException as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise last_err

    def post_bytes(self, url, params, data):
        """POST a WebForms postback; returns raw bytes (no cache)."""
        last_err = None
        for attempt in range(3):
            try:
                r = self.session.post(url, params=params, data=data, timeout=120)
                r.raise_for_status()
                time.sleep(self.sleep_s)
                return r.content
            except requests.RequestException as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise last_err

    def get_json(self, url, params, fresh=False):
        """GET returning parsed JSON. Empty/failed responses return []."""
        path = self._cache_path(url, params, ".json")
        if not fresh and not self.refresh and path.exists():
            text = path.read_text(encoding="utf-8")
        else:
            text = None
        if text is None:
            text = self.get(url, params, fresh=fresh)
            # get() saved it as .html; store the canonical copy as .json
            path.write_text(text, encoding="utf-8")
        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log(f"WARNING: non-JSON response from {url} {params}")
            return []
        return data if isinstance(data, list) else []


def parse_race_buttons(page_html, page_type, page_params, county_name=""):
    """Parse one resultsSW.aspx page into Race objects.

    Each race lives in a `display-results-box-wrapper` div; the box's first
    <h1> is the race title (later h1s are candidate/vote pairs). Every export
    button carries raceid/party/officeseqno/countyid attributes; the County
    and Precinct buttons for a race repeat the same attributes, so races are
    deduped on (raceid, party, osn).
    """
    races = {}
    boxes = re.split(r'class="display-results-box-wrapper"', page_html)
    for chunk in boxes[1:]:
        h1s = [strip_tags(m) for m in re.findall(r"<h1[^>]*>(.*?)</h1>", chunk, re.S)]
        h1s = [h for h in h1s if h]
        if not h1s:
            continue
        title = h1s[0]
        # contest id for SearchResults.aspx (from the box's share link); the
        # per-contest page serves an XLSX export even for races the JSON API
        # returns nothing for
        m_share = re.search(r"SearchResults\.aspx\?ID=(\d+)", chunk)
        search_id = m_share.group(1) if m_share else ""
        # candidate/vote pairs shown in the box (used as a fallback when the
        # JSON API has no data for the race)
        cands, pending = [], None
        for h in h1s[1:]:
            if re.fullmatch(r"[\d,\.]+%?", h) or h == "*":
                if pending:
                    cands.append((pending, h.replace(",", "")))
                    pending = None
            else:
                pending = h
        for tag in re.findall(r'<input[^>]*class="export-button"[^>]*>', chunk):
            a = _attrs(tag)
            try:
                raceid, osn = int(a.get("raceid", "")), int(a.get("officeseqno", ""))
            except ValueError:
                continue
            key = (raceid, a.get("party", ""), osn)
            if key not in races:
                races[key] = Race(raceid=raceid, osn=osn,
                                 party=a.get("party", ""),
                                 countyid=a.get("countyid", ""),
                                 page_type=page_type, title=title,
                                 search_id=search_id,
                                 page_params=dict(page_params),
                                 county_name=county_name,
                                 page_candidates=cands)
    return list(races.values())


def enumerate_races(fetcher, args):
    """Enumerate every race on the site for the requested election."""
    eid = args.eid
    archive = args.eid is not None

    def page_params(extra):
        p = {"map": "CTY"}
        p.update(extra)
        if archive:
            p["eid"] = eid
        return p

    categories = args.categories
    races = {}

    def add(new_races):
        for r in new_races:
            # raceid is unique per contest, so drop countyid from the key:
            # the same race shows up on category pages with a county code
            # ("01 ") and on SearchResults with a district label.
            key = (r.raceid, r.party, r.osn)
            races.setdefault(key, r)

    for t in categories:
        if t == "CTY":
            continue
        p = page_params({"type": t})
        html = fetcher.get(SITE + "resultsSW.aspx", p)
        found = parse_race_buttons(html, t, p)
        add(found)
        log(f"  {t}: {len(found)} races")
        if not found:
            log(f"  NOTE: no races found on {t} page (may be an empty category)")

    if "CTY" in categories:
        list_html = fetcher.get(SITE + "resultsList.aspx",
                                page_params({"type": "cty"}))
        links = re.findall(r'resultsSW\.aspx\?([^"]+)', list_html)
        seen_county = 0
        for href in links:
            href = html_lib.unescape(href)
            m_cty = re.search(r"cty=([0-9]+)\s*", href)
            m_name = re.search(r"name=([^&]+)", href)
            if not m_cty:
                continue
            code = m_cty.group(1)
            name = m_name.group(1) if m_name else ""
            # NB: the page's cty codes are NOT the API county codes (Santa Fe
            # is cty=01 here but county 49 in the API), so match names too.
            if args.counties and code not in args.counties \
                    and name.upper() not in args.counties:
                continue
            p = page_params({"type": "CTYSPEC", "cty": code + " ", "name": name})
            html = fetcher.get(SITE + "resultsSW.aspx", p)
            found = parse_race_buttons(html, "CTY", p, county_name=name)
            add(found)
            seen_county += 1
        log(f"  CTY: {seen_county} county pages scraped")

    # Catch-all: GetCandidates lists every contest's SearchResults id.
    # The category pages cap out — the LGX page shows only the first 25
    # senate and 25 house districts — so enumerate anything the pages
    # missed from its per-contest pages (same race-box markup).
    data = fetcher.get_json(API + "GetCandidates",
                            {"ElectionType": args.election_type,
                             "ElectionID": eid if archive else 0})
    seen_ids, added = set(), 0
    for d in data:
        cid = d.get("ID")
        if cid is None or cid in seen_ids:
            continue
        seen_ids.add(cid)
        p = {"ID": cid}
        if archive:
            p["eid"] = eid
        page_html = fetcher.get(SITE + "SearchResults.aspx", p)
        for r in parse_race_buttons(page_html, "", p):
            r.page_type = searchresults_page_type(r.title)
            r.search_id = str(cid)
            key = (r.raceid, r.party, r.osn)
            if key not in races:
                races[key] = r
                added += 1
    log(f"  SearchResults: {len(seen_ids)} contest pages, {added} new races")
    return list(races.values())


def searchresults_page_type(title):
    """Best API `type` for a race only seen on a SearchResults page."""
    t = title.upper()
    if "STATE SENATOR" in t or "STATE REPRESENTATIVE" in t:
        return "LGX"
    if "METROPOLITAN" in t:
        return "JMC"
    if "DISTRICT ATTORNEY" in t:
        return "DAX"
    if "MAGISTRATE" in t:
        return "MGX"
    if "PUBLIC EDUCATION" in t:
        return "ECX"
    if "DISTRICT COURT" in t:
        return "JDX"
    if "MUNICIPAL" in t or t.startswith("CITY OF"):
        return "MUX"
    if "HOSPITAL" in t:
        return "HDX"
    if "CONSERVATION" in t:
        return "SWX"
    if "COLLEGE" in t:
        return "CLX"
    if "COUNTY" in t:
        return "CTY"
    return "JDX"  # judicial retention and other dead-in-archive contests


def candidates_cross_check(fetcher, args, races):
    """Compare enumerated races against the API's candidate list."""
    eid = args.eid if args.eid is not None else 0
    data = fetcher.get_json(API + "GetCandidates",
                            {"ElectionType": args.election_type, "ElectionID": eid})
    if not data:
        log("NOTE: GetCandidates returned nothing; skipping cross-check")
        return
    descs = {re.sub(r"\s+", " ", (d.get("desc") or "")).strip().upper() for d in data}
    titles = {re.sub(r"\s+", " ", strip_county_suffix(r.title)).strip().upper() for r in races}
    covered = {d for d in descs if any(d in t or t in d for t in titles)}
    missing = descs - covered
    if missing:
        log(f"NOTE: {len(missing)} GetCandidates contests not matched to an enumerated race:")
        for d in sorted(missing)[:20]:
            log(f"    - {d}")
    else:
        log(f"  cross-check: all {len(descs)} GetCandidates contests covered")


def party_map_from_candidates(fetcher, args):
    """candidate name (upper) -> party code, from the GetCandidates list."""
    eid = args.eid if args.eid is not None else 0
    data = fetcher.get_json(API + "GetCandidates",
                            {"ElectionType": args.election_type, "ElectionID": eid})
    pmap = {}
    for d in data:
        name = (d.get("name") or "").strip().upper()
        party = PARTY_CODES.get((d.get("Party") or "").strip(), "")
        if name:
            pmap.setdefault(name, party)
    return pmap


def api_url_and_params(race, category, args):
    archive = args.eid is not None
    # The API only accepts a 2-digit county code ("01 ") for county races;
    # SearchResults buttons carry district labels ("DISTRICT 40") there,
    # which return nothing — anything else means "all counties".
    county = race.countyid or "0"
    if not re.fullmatch(r"\d{2}\s*", county):
        county = "0"
    params = {
        "type": race.page_type,
        "category": category,
        "raceID": race.raceid,
        "osn": race.osn,
        "county": county,
        "party": race.party or "0",
    }
    if archive:
        params["electionID"] = args.eid
        return API + "GetMapDataArchive", params
    return API + "GetMapData", params


def hidden_fields(page_html):
    fields = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', page_html):
        a = _attrs(m.group(0))
        if a.get("name"):
            fields[a["name"]] = html_lib.unescape(a.get("value", ""))
    return fields


def parse_workbook(data):
    """Minimal XLSX reader: {sheet name: [[cell values as strings]]}."""
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    zf = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    RNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    rel_targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{RNS}Relationship")}
    sheets = {}
    for sheet in wb.iter(f"{NS}sheet"):
        name = sheet.get("name")
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_targets.get(rid, "")
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        if path not in zf.namelist():
            continue
        rows = []
        for row in ET.fromstring(zf.read(path)).iter(f"{NS}row"):
            cells = []
            for c in row.iter(f"{NS}c"):
                v = c.find(f"{NS}v")
                text = v.text if v is not None else ""
                if c.get("t") == "s" and text:
                    text = shared[int(text)]
                elif c.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                try:
                    col = int(re.sub(r"[A-Z]", "", c.get("r", "A1")))
                except ValueError:
                    col = len(cells) + 1
                while len(cells) < col - 1:
                    cells.append("")
                cells.append(text or "")
            rows.append(cells)
        sheets[name] = rows
    return sheets


def workbook_rows_to_api_rows(sheets, party_map):
    """Interpret a per-contest SoS export workbook as API-like result rows.

    Layout (observed on SearchResults.aspx exports): one sheet per county,
    a header row containing a 'Precinct' cell with candidate names to its
    right, then data rows whose precinct/vote cells are progressively
    indented — so the leading non-empty cells of each row are the precinct
    name followed by one vote cell per candidate, ending with a TOTALS row
    (kept verbatim; callers decide what to do with it).
    """
    out = []
    for sheet_name, rows in sheets.items():
        county = sheet_name.strip()
        if county not in COUNTIES:
            continue  # skip summary sheets like "County Results"
        header_i, prec_col = None, None
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                if str(cell).strip().lower() == "precinct":
                    header_i, prec_col = i, j
                    break
            if header_i is not None:
                break
        if header_i is None:
            continue
        candidates = [str(c).strip() for c in rows[header_i][prec_col + 1:]
                      if str(c).strip()]
        candidates = [c for c in candidates if not re.fullmatch(r"[\d,\.\%]+", c)]
        if not candidates:
            continue
        for row in rows[header_i + 1:]:
            cells = [str(c).strip() for c in row if str(c).strip()]
            if len(cells) < 1 + len(candidates):
                continue  # blank or stray note rows
            precinct, votes = cells[0], cells[1:1 + len(candidates)]
            for name, v in zip(candidates, votes):
                out.append({
                    "CountyName": county,
                    "PrecinctName": precinct,
                    "PartyCode": party_map.get(name.upper(), ""),
                    "calcCandidate": name,
                    "calcCandidateVotes": v,
                })
    return out


def searchresults_xlsx_rows(fetcher, race, party_map):
    """Fetch a race's rows from its SearchResults.aspx XLSX export.

    The per-contest SearchResults page serves a WebForms postback that
    returns the real precinct workbook — including for races the JSON API
    returns nothing for (2024-archive county commissioner races, county
    bond questions). The workbook is one sheet per county with per-precinct
    rows ending in a TOTALS row; rows keep PrecinctName so callers can pick
    precinct rows or county totals.
    """
    if not race.search_id:
        raise RuntimeError("race box has no SearchResults contest id")
    params = {"ID": race.search_id}
    if ARGS.eid is not None:
        params["eid"] = ARGS.eid
    # The page must be fetched in the same session as the postback: ASP.NET
    # rejects __VIEWSTATE from another session's cached page ("An error has
    # occured"), so never serve this one from the disk cache.
    page_html = fetcher.get(SITE + "SearchResults.aspx", params, fresh=True)
    m = re.search(r'<input[^>]*class="export-button"[^>]*>', page_html)
    if not m:
        raise RuntimeError("SearchResults page has no export button "
                           "(contest may be a dead archive record)")
    event_target = _attrs(m.group(0)).get("name")
    if not event_target:
        raise RuntimeError("export button has no name")
    form = {"__EVENTTARGET": event_target, "__EVENTARGUMENT": ""}
    form.update(hidden_fields(page_html))
    content = fetcher.post_bytes(SITE + "SearchResults.aspx", params, form)
    if content[:2] != b"PK":
        snippet = content[:200].decode("utf-8", "replace")
        raise RuntimeError(f"postback did not return an XLSX file: {snippet}")
    rows = workbook_rows_to_api_rows(parse_workbook(content), party_map)
    if not rows:
        raise RuntimeError("workbook parsed but no data rows recognized")
    return rows


def fetch_race_rows(fetcher, race, category, party_map):
    """Fetch one race's rows at one level; fall back when the API is empty.

    Returns (rows, source) where source is "api", "page-totals",
    "xlsx-precinct"/"xlsx-totals"/"xlsx-aggregated", or None (no data
    anywhere on the site).
    """
    url, params = api_url_and_params(race, category, ARGS)
    rows = fetcher.get_json(url, params)
    if rows:
        return rows, "api"
    # Empty API response. County races may still have page totals.
    if category == "CTY" and race.page_type == "CTY" and race.page_candidates \
            and race.county_name:
        out = []
        for name, votes in race.page_candidates:
            if re.fullmatch(r"[\d\*]+", votes):
                out.append({
                    "CountyName": race.county_name,
                    "PartyCode": party_map.get(name.upper(), ""),
                    "calcCandidate": name,
                    "calcCandidateVotes": votes,
                })
        if out:
            return out, "page-totals"
    # SearchResults XLSX export (real data for races the archive JSON API
    # returns nothing for). Fetched once per race — the workbook carries
    # both precinct rows and county totals.
    try:
        if getattr(race, "_xlsx_rows", None) is None:
            race._xlsx_rows = searchresults_xlsx_rows(fetcher, race, party_map)
        rows = race._xlsx_rows
    except Exception as e:
        log(f"WARNING: SearchResults xlsx fallback failed for "
            f"raceid={race.raceid} ({race.title!r}) category={category}: {e}")
        return [], None
    totals = [dict(r, PrecinctName=None) for r in rows
              if DROP_PRECINCT_RE.match((r.get("PrecinctName") or "").strip())]
    if category == "CTY":
        if totals:
            return totals, "xlsx-totals"
        # No TOTALS row: sum the precinct rows. Masked ('*') precincts
        # cannot be summed, so this is a lower bound — flag it in the source.
        agg = {}
        for r in rows:
            key = (r["CountyName"], r["calcCandidate"], r["PartyCode"])
            v = (r.get("calcCandidateVotes") or "").strip()
            agg.setdefault(key, 0)
            if v.isdigit():
                agg[key] += int(v)
        return [{"CountyName": k[0], "PrecinctName": None,
                 "PartyCode": k[2], "calcCandidate": k[1],
                 "calcCandidateVotes": str(v)} for k, v in sorted(agg)], \
            "xlsx-aggregated"
    return [r for r in rows
            if not DROP_PRECINCT_RE.match((r.get("PrecinctName") or "").strip())], \
        "xlsx-precinct"


def rows_to_records(race, rows, level, unmapped):
    """Transform API-like rows into OpenElections CSV records."""
    office, district, mapped = map_office(race.title)
    if not mapped:
        unmapped.add(race.title.strip())
    # Some counties (Lincoln in 2022/2024) report a precinct twice per race:
    # once as bare digits ("23") and once zero-padded ("PRECINCT 023"), with
    # identical values. Counties that use bare digits exclusively (Colfax) have
    # no padded twins and keep every row. Only exact (candidate, votes) twins
    # are dropped, so a bare row whose padded sibling disagrees survives loudly.
    padded_twins = set()
    if level == "precinct":
        for row in rows:
            pn = (row.get("PrecinctName") or "").strip()
            m = re.fullmatch(r"PRECINCT\s+(\d+)", pn, re.I)
            if m:
                cand = re.sub(r"\s+", " ", (row.get("calcCandidate") or "")).strip()
                if cand.upper() in ("YES", "NO"):
                    cand = cand.title()
                if office == "President" and " AND " in cand:
                    cand = cand.split(" AND ")[0].strip()
                votes = row.get("calcCandidateVotes")
                padded_twins.add(((row.get("CountyName") or "").strip(), int(m.group(1)),
                                  cand, "" if votes is None else str(votes).strip()))
    records, skipped = [], 0
    for row in rows:
        county = (row.get("CountyName") or "").strip()
        if county not in COUNTIES:
            skipped += 1
            continue
        cand = re.sub(r"\s+", " ", (row.get("calcCandidate") or "")).strip()
        votes = row.get("calcCandidateVotes")
        votes = "" if votes is None else str(votes).strip()
        party = (row.get("PartyCode") or "").strip()
        if cand.upper() in ("YES", "NO"):
            cand = cand.title()
            party = "NA"
        # President rows are full tickets; keep the top of the ticket.
        if office == "President" and " AND " in cand:
            cand = cand.split(" AND ")[0].strip()
        if level == "county":
            records.append([county, office, district, party, cand, votes])
        else:
            precinct = re.sub(r"\s+", " ", (row.get("PrecinctName") or "")).strip()
            if not precinct or DROP_PRECINCT_RE.match(precinct):
                skipped += 1
                continue
            m = re.fullmatch(r"(\d+)", precinct)
            if m and (county, int(m.group(1)), cand, votes) in padded_twins:
                skipped += 1
                continue
            records.append([county, precinct, office, district, party, cand, votes])
    return records, skipped


def write_csv(path, records, level):
    header = (["county", "office", "district", "party", "candidate", "votes"]
              if level == "county" else
              ["county", "precinct", "office", "district", "party", "candidate", "votes"])
    records.sort()
    # LF line endings match the repo's hand-built files (csv default is CRLF)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(header)
        w.writerows(records)
    return len(records)


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compare_precinct(new_path, old_path, county_path):
    """Diff a generated precinct CSV against an existing OpenElections file."""
    new, old = load_csv(new_path), load_csv(old_path)

    def office_key(r):
        return (r["office"], r["district"])

    old_offices = {office_key(r) for r in old}
    new_offices = {office_key(r) for r in new}
    shared = old_offices & new_offices
    print("== office coverage (old file vs new) ==")
    for k in sorted(old_offices | new_offices):
        co = sum(1 for r in old if office_key(r) == k)
        cn = sum(1 for r in new if office_key(r) == k)
        marker = "" if k in old_offices and k in new_offices else "  <-- only in " + ("old" if k in old_offices else "new")
        print(f"  {k[0]!r} dist={k[1]!r}: old={co} rows, new={cn} rows{marker}")
    if not shared:
        print("no shared offices; nothing to compare")
        return

    def in_shared(r):
        return office_key(r) in shared

    def votes_key(r, level):
        parts = [r["county"], r.get("precinct", ""), r["office"], r["district"], r["party"], r["votes"]]
        return tuple(parts)

    new_s = {votes_key(r, "new") for r in new if in_shared(r)}
    old_s = {votes_key(r, "old") for r in old if in_shared(r)}
    only_new, only_old = new_s - old_s, old_s - new_s
    print(f"== exact (county,precinct,office,district,party,votes) over shared offices ==")
    print(f"  rows only in new: {len(only_new)}; only in old: {len(only_old)}")
    for label, s in (("new", only_new), ("old", only_old)):
        for t in sorted(s)[:5]:
            print(f"    only in {label}: {t}")

    # candidate-level comparison, tolerant of casing and the President ticket
    def norm_cand(r):
        c = r["candidate"].upper()
        if r["office"] == "President" and " AND " in c:
            c = c.split(" AND ")[0]
        return c

    def cand_key(r):
        return (r["county"], r.get("precinct", ""), r["office"], r["district"], norm_cand(r))

    new_c = {cand_key(r): r["votes"] for r in new if in_shared(r)}
    old_c = {cand_key(r): r["votes"] for r in old if in_shared(r)}
    vote_mismatch = [(k, old_c[k], new_c.get(k)) for k in old_c if k in new_c and old_c[k] != new_c.get(k)]
    print(f"== candidate-level vote mismatches (shared offices, normalized names): {len(vote_mismatch)} ==")
    for k, o, n in vote_mismatch[:10]:
        print(f"    {k}: old={o} new={n}")

    if county_path:
        county_rows = load_csv(county_path)
        print("== cross-foot: precinct sums (excl. '*') vs county totals ==")
        prec_totals = {}
        for r in new:
            if in_shared(r) and r["votes"] not in ("*", ""):
                prec_totals[(r["county"], r["office"], r["district"], r["candidate"].upper())] = \
                    prec_totals.get((r["county"], r["office"], r["district"], r["candidate"].upper()), 0) + int(r["votes"])
        cty_totals = {(r["county"], r["office"], r["district"], r["candidate"].upper()): int(r["votes"])
                      for r in county_rows if in_shared(r) and r["votes"] not in ("*", "") and r["votes"].isdigit()}
        bad = 0
        for k, total in sorted(prec_totals.items()):
            cty = cty_totals.get(k)
            if cty is not None and cty != total:
                bad += 1
                if bad <= 10:
                    print(f"    {k}: precinct sum={total} county={cty}")
        checked = sum(1 for k in prec_totals if k in cty_totals)
        print(f"  checked {checked} county/candidate combos; {bad} mismatched")


def check_election_title(fetcher, args):
    """Confirm the election we're scraping is the one the operator asked for."""
    params = {"eid": args.eid} if args.eid is not None else None
    html = fetcher.get(SITE + "Default.aspx", params, fresh=True)
    m = re.search(r"<h2[^>]*>\s*\d{4} (General|Primary|Special) ([^<]+?)</h2>", html, re.I | re.S)
    title = strip_tags(m.group(0)) if m else "(unknown)"
    log(f"  site election: {title}")
    want_date = args.date.strftime("%B %-d, %Y")
    if want_date.lower() not in title.lower():
        log(f"WARNING: site title does not mention {want_date} -- verify --date/--election-type!")
    if args.election_type.lower() not in title.lower():
        log(f"WARNING: site title does not mention '{args.election_type}' -- verify --election-type!")
    return title


ARGS = None  # set in main(); lets fetch_race_rows see the CLI options


def main():
    global ARGS
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--eid", type=int, help="archive election id (e.g. 2882 for the 2024 general)")
    mode.add_argument("--live", action="store_true", help="scrape the current live election")
    p.add_argument("--election-type", required=True, choices=["General", "Primary", "Special"])
    p.add_argument("--date", required=True, type=lambda s: datetime.date.fromisoformat(s),
                   help="election date, YYYY-MM-DD (used in the output filename)")
    p.add_argument("--outdir", help="output directory (default: year of --date)")
    p.add_argument("--categories", default=",".join(PAGE_TYPES) + ",CTY",
                   help="comma-separated page types to include (default: all + CTY)")
    p.add_argument("--counties", help="comma-separated 2-digit SoS county codes or county names (CTY pages only)")
    p.add_argument("--dry-run", action="store_true", help="enumerate races and exit")
    p.add_argument("--refresh", action="store_true", help="bypass the cache for this run")
    p.add_argument("--cache-dir", default=".cache")
    p.add_argument("--sleep", type=float, default=1.0)
    p.add_argument("--strict", action="store_true", help="fail on unmapped race titles")
    p.add_argument("--compare", help="diff generated precinct CSV against this existing file")
    p.add_argument("--force", action="store_true",
                   help="overwrite output CSVs even if they already exist (default: fail first)")
    args = p.parse_args()
    ARGS = args

    args.categories = [c.strip().upper() for c in args.categories.split(",") if c.strip()]
    args.counties = [c.strip().upper() for c in args.counties.split(",")] if args.counties else []

    outdir = Path(args.outdir or str(args.date.year))
    outdir.mkdir(parents=True, exist_ok=True)
    slug = args.election_type.lower()
    stem = f"{args.date.strftime('%Y%m%d')}__nm__{slug}"
    county_csv = outdir / f"{stem}__county.csv"
    precinct_csv = outdir / f"{stem}__precinct.csv"
    for path in (county_csv, precinct_csv):
        if path.exists() and not args.force:
            sys.exit(f"REFUSING to overwrite existing {path} "
                     f"(use --force, or --outdir to a scratch directory)")

    log(f"election: {'archive eid=' + str(args.eid) if args.eid else 'LIVE'} "
        f"{args.election_type} {args.date} -> {outdir}/")
    fetcher = Fetcher(args.cache_dir, args.sleep, refresh=args.refresh)
    check_election_title(fetcher, args)

    log("enumerating races...")
    races = enumerate_races(fetcher, args)
    log(f"  total: {len(races)} races "
        f"(across {len({(r.raceid, r.osn) for r in races})} race ids)")
    if args.dry_run:
        print(f"{'type':6} {'raceid':7} {'osn':5} {'party':5} {'cty':5} office | district | title")
        for r in sorted(races, key=lambda r: (r.page_type, r.title)):
            office, district, mapped = map_office(r.title)
            flag = "" if mapped else "  [unmapped]"
            print(f"{r.page_type:6} {r.raceid:<7} {r.osn:<5} {r.party or '-':5} "
                  f"{r.countyid.strip() or '-':5} {office} | {district} |{flag} {r.title.strip()}")
        return

    candidates_cross_check(fetcher, args, races)
    party_map = party_map_from_candidates(fetcher, args)

    county_records, precinct_records = [], []
    unmapped_titles, empty_races, failed_races = set(), [], []
    sources = {}
    log("fetching results per race (county level, then precinct level)...")
    for i, race in enumerate(races, 1):
        for level, sink in (("CTY", county_records), ("PREC", precinct_records)):
            rows, source = fetch_race_rows(fetcher, race, level, party_map)
            sources[source] = sources.get(source, 0) + 1
            if not rows:
                empty_races.append((race, level))
                if race.page_type in FAIL_EMPTY_TYPES:
                    failed_races.append((race, level))
                continue
            records, skipped = rows_to_records(race, rows,
                                               "county" if level == "CTY" else "precinct",
                                               unmapped_titles)
            if skipped:
                log(f"  NOTE: dropped {skipped} rows from raceid={race.raceid} "
                    f"({race.title.strip()!r}) at {level}")
            sink.extend(records)
        if i % 25 == 0:
            log(f"  ...{i}/{len(races)} races done")

    log(f"row sources: {sources}")
    log(f"county records: {len(county_records)}; precinct records: {len(precinct_records)}")

    # county CSV first, then precinct CSV
    n = write_csv(county_csv, county_records, "county")
    log(f"wrote {county_csv} ({n} rows)")
    n = write_csv(precinct_csv, precinct_records, "precinct")
    log(f"wrote {precinct_csv} ({n} rows)")

    print("\n== SUMMARY ==")
    print(f"races enumerated: {len(races)}")
    print(f"county records:  {len(county_records)} -> {county_csv}")
    print(f"precinct records: {len(precinct_records)} -> {precinct_csv}")
    if empty_races:
        print(f"races with no data ({len(empty_races)}):")
        for race, level in empty_races:
            print(f"    {race.page_type} raceid={race.raceid} osn={race.osn} "
                  f"party={race.party!r} county={race.countyid.strip()!r} "
                  f"[{level}] {race.title.strip()}")
    if unmapped_titles:
        print(f"unmapped race titles ({len(unmapped_titles)}) -- emitted verbatim:")
        for t in sorted(unmapped_titles):
            print(f"    - {t}")
    if failed_races:
        print(f"FAILED: {len(failed_races)} federal/statewide/legislative/judicial races "
              f"returned no data:")
        for race, level in failed_races:
            print(f"    {race.page_type} raceid={race.raceid} [{level}] {race.title.strip()}")

    if args.compare:
        print(f"\n== COMPARE: {precinct_csv} vs {args.compare} ==")
        compare_precinct(precinct_csv, args.compare, county_csv)

    if failed_races or (args.strict and unmapped_titles):
        sys.exit(1)


if __name__ == "__main__":
    main()