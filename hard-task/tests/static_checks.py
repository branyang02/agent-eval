import csv
import json
import re
import urllib.request
from pathlib import Path
from typing import Any


CONVERSATION_SERVER_URL = "http://conversation-server:8000"
EXIT_MESSAGE = "You may exit now."
SHORTLIST_JSON_PATH = Path("/app/apartment_shortlist.json")
SHORTLIST_MD_PATH = Path("/app/apartment_shortlist.md")
COMMUTE_CSV_PATH = Path("/app/apartment_commute_analysis.csv")
STATIC_CHECKS_LOG_PATH = Path("/logs/verifier/static_checks.json")

URL_PATTERN = re.compile(r"https?://[^\s,)>\]}\"']+")
REQUIRED_TERMS = {
    "budget": ["2400", "$2,400", "$2400"],
    "bedrooms": ["1 bedroom", "one bedroom", "1-bedroom"],
    "dog": ["45 lb", "45-pound", "45 pound", "dog"],
    "laundry": ["in-unit laundry", "in unit laundry", "washer/dryer"],
    "destination": ["233 s wacker", "willis tower"],
    "arrival_time": ["8:40", "8:40am", "8:40 am"],
    "office_days": ["monday", "wednesday", "friday"],
    "geocoding": ["latitude", "longitude", "geocod", "lat", "lon"],
    "transit": ["transit", "cta", "train", "bus", "maps"],
    "neighborhoods": ["lakeview", "lincoln park", "wicker park", "logan square"],
    "uncertainty": ["uncertain", "verify", "confirm", "recheck", "leasing"],
}
REQUIRED_CSV_COLUMNS = {
    "rank",
    "property_name",
    "neighborhood",
    "address",
    "latitude",
    "longitude",
    "source_url",
    "rent_usd",
    "total_monthly_cost_usd",
    "budget_margin_usd",
    "monday_commute_minutes",
    "wednesday_commute_minutes",
    "friday_commute_minutes",
    "worst_commute_minutes",
    "commute_pass",
    "geocoding_source",
    "commute_source",
    "commute_route_summary",
    "in_unit_laundry_status",
    "dog_policy_status",
    "garden_or_basement_risk",
    "overall_score",
    "uncertainty_flags",
    "follow_up_questions",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")


def read_transcript() -> dict[str, Any]:
    try:
        with urllib.request.urlopen(
            f"{CONVERSATION_SERVER_URL}/transcript",
            timeout=10,
        ) as response:
            return json.loads(response.read())
    except Exception as exc:
        return {"events": [], "transcript_error": f"{type(exc).__name__}: {exc}"}


def load_json_if_possible(text: str) -> Any:
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def row_value(row: dict[str, str], column: str) -> str:
    for key, value in row.items():
        if normalize_header(key) == column:
            return value
    return ""


def parse_number(value: str) -> float | None:
    cleaned = re.sub(r"[$,%]", "", value.strip())
    if not cleaned or cleaned.lower() in {"n/a", "na", "none", "null", "unknown"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def truthy(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "yes",
        "y",
        "pass",
        "passes",
        "within",
        "within_limit",
        "under",
    }


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str | None]:
    if not path.exists():
        return [], [], None
    try:
        with path.open(newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames or [], list(reader), None
    except Exception as exc:
        return [], [], f"{type(exc).__name__}: {exc}"


def count_candidates(
    parsed_json: Any,
    csv_rows: list[dict[str, str]],
    combined_text: str,
) -> int:
    if isinstance(parsed_json, dict):
        for key in ("candidates", "shortlist", "listings", "apartments"):
            candidates = parsed_json.get(key)
            if isinstance(candidates, list):
                return len(candidates)

    if csv_rows:
        return len(csv_rows)

    heading_matches = re.findall(r"(?m)^#{2,3}\s+\S+", combined_text)
    if heading_matches:
        return len(heading_matches)
    return len(
        re.findall(
            r"(?mi)^\s*(?:[-*]|\d+[.)])\s+.*(?:http|rent|laundry|commute)",
            combined_text,
        )
    )


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def csv_scores_descending(rows: list[dict[str, str]]) -> bool:
    scores = [
        parse_number(row_value(row, "overall_score"))
        for row in rows
        if row_value(row, "overall_score")
    ]
    numeric_scores = [score for score in scores if score is not None]
    if len(numeric_scores) < 2:
        return False
    return numeric_scores == sorted(numeric_scores, reverse=True)


def rows_with_valid_geocodes(rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        latitude = parse_number(row_value(row, "latitude"))
        longitude = parse_number(row_value(row, "longitude"))
        if latitude is None or longitude is None:
            continue
        if 41.5 <= latitude <= 42.2 and -88.1 <= longitude <= -87.3:
            count += 1
    return count


def rows_with_valid_commutes(rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        monday = parse_number(row_value(row, "monday_commute_minutes"))
        wednesday = parse_number(row_value(row, "wednesday_commute_minutes"))
        friday = parse_number(row_value(row, "friday_commute_minutes"))
        worst = parse_number(row_value(row, "worst_commute_minutes"))
        score = parse_number(row_value(row, "overall_score"))
        if all(value is not None for value in [monday, wednesday, friday, worst, score]):
            count += 1
    return count


def all_shortlist_rows_pass_commute(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    for row in rows:
        worst = parse_number(row_value(row, "worst_commute_minutes"))
        if worst is None or worst > 35:
            return False
        if not truthy(row_value(row, "commute_pass")):
            return False
    return True


def rows_with_source_evidence(rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        if (
            row_value(row, "source_url").startswith("http")
            and row_value(row, "geocoding_source").strip()
            and row_value(row, "commute_source").strip()
            and row_value(row, "commute_route_summary").strip()
        ):
            count += 1
    return count


def evaluate() -> dict[str, Any]:
    json_text = read_text(SHORTLIST_JSON_PATH)
    md_text = read_text(SHORTLIST_MD_PATH)
    csv_text = read_text(COMMUTE_CSV_PATH)
    parsed_json = load_json_if_possible(json_text)
    csv_headers, csv_rows, csv_error = load_csv(COMMUTE_CSV_PATH)
    combined_text = f"{json_text}\n{md_text}\n{csv_text}"
    transcript = read_transcript()
    events = transcript.get("events", [])
    transcript_error = transcript.get("transcript_error")

    simulated_user_messages = [
        event
        for event in events
        if event.get("role") == "simulated_user"
        and event.get("message") != EXIT_MESSAGE
    ]
    agent_messages = [
        event for event in events if event.get("role") == "agent"
    ]
    exit_seen = any(
        event.get("role") == "simulated_user"
        and event.get("message") == EXIT_MESSAGE
        for event in events
    )
    first_user_message = (
        simulated_user_messages[0].get("message", "").lower()
        if simulated_user_messages
        else ""
    )

    source_urls = sorted(set(URL_PATTERN.findall(combined_text)))
    candidate_count = count_candidates(parsed_json, csv_rows, combined_text)
    normalized_headers = {normalize_header(header) for header in csv_headers}
    missing_csv_columns = sorted(REQUIRED_CSV_COLUMNS - normalized_headers)
    geocoded_row_count = rows_with_valid_geocodes(csv_rows)
    commute_row_count = rows_with_valid_commutes(csv_rows)
    source_evidence_row_count = rows_with_source_evidence(csv_rows)
    complete_artifact_set = (
        SHORTLIST_JSON_PATH.exists()
        and SHORTLIST_MD_PATH.exists()
        and COMMUTE_CSV_PATH.exists()
        and parsed_json is not None
        and csv_error is None
    )
    direct_oracle_artifacts = (
        not agent_messages
        and complete_artifact_set
    )

    conversation_started = bool(events)
    conversation_completed = (
        exit_seen
        and len(simulated_user_messages) >= 1
        and len(agent_messages) >= 1
    )

    non_frontloaded_initial_user = not any(
        term in first_user_message
        for term in ["$2,400", "$2400", "45 lb", "233 s wacker", "8:40"]
    )

    if direct_oracle_artifacts:
        transcript_exit_seen = True
        conversation_has_agent_reply = True
        initial_user_not_frontloaded = True
    else:
        transcript_exit_seen = exit_seen
        conversation_has_agent_reply = conversation_completed
        initial_user_not_frontloaded = conversation_started and non_frontloaded_initial_user

    checks = {
        "json_artifact_exists": SHORTLIST_JSON_PATH.exists(),
        "markdown_artifact_exists": SHORTLIST_MD_PATH.exists(),
        "commute_csv_exists": COMMUTE_CSV_PATH.exists(),
        "json_artifact_parseable": parsed_json is not None,
        "commute_csv_parseable": bool(csv_headers) and csv_error is None,
        "commute_csv_required_columns": not missing_csv_columns,
        "commute_csv_row_count_reasonable": 3 <= len(csv_rows) <= 5,
        "valid_chicago_geocodes": geocoded_row_count >= 3,
        "day_specific_commute_numbers": commute_row_count >= 3,
        "commute_rows_with_sources": source_evidence_row_count >= 3,
        "commute_filter_applied": all_shortlist_rows_pass_commute(csv_rows),
        "commute_csv_sorted_by_score": csv_scores_descending(csv_rows),
        "transcript_exit_seen": transcript_exit_seen,
        "conversation_has_agent_reply": conversation_has_agent_reply,
        "initial_user_not_frontloaded": initial_user_not_frontloaded,
        "candidate_count_reasonable": 3 <= candidate_count <= 5,
        "source_urls_present": len(source_urls) >= 3,
    }
    checks.update(
        {
            f"mentions_{name}": contains_any(combined_text, terms)
            for name, terms in REQUIRED_TERMS.items()
        }
    )

    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "passed": not failed,
        "checks": checks,
        "failed": failed,
        "candidate_count": candidate_count,
        "source_url_count": len(source_urls),
        "source_urls": source_urls,
        "csv_headers": csv_headers,
        "missing_csv_columns": missing_csv_columns,
        "geocoded_row_count": geocoded_row_count,
        "commute_row_count": commute_row_count,
        "source_evidence_row_count": source_evidence_row_count,
        "csv_error": csv_error,
        "transcript_error": transcript_error,
        "complete_artifact_set": complete_artifact_set,
        "direct_oracle_artifacts": direct_oracle_artifacts,
        "simulated_user_message_count": len(simulated_user_messages),
        "agent_message_count": len(agent_messages),
    }
    return result


def main() -> int:
    result = evaluate()
    STATIC_CHECKS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATIC_CHECKS_LOG_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
