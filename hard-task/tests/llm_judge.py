import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONVERSATION_SERVER_URL = "http://conversation-server:8000"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SHORTLIST_JSON_PATH = Path("/app/apartment_shortlist.json")
SHORTLIST_MD_PATH = Path("/app/apartment_shortlist.md")
COMMUTE_CSV_PATH = Path("/app/apartment_commute_analysis.csv")
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "llm_judge_prompt.md"
JUDGE_LOG_PATH = Path("/logs/verifier/llm_judge.json")


@dataclass(frozen=True)
class Config:
    model: str
    api_key: str


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def read_json(url: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def read_transcript() -> dict[str, Any]:
    try:
        return read_json(f"{CONVERSATION_SERVER_URL}/transcript")
    except Exception as exc:
        return {"events": [], "transcript_error": f"{type(exc).__name__}: {exc}"}


def read_artifact(path: Path) -> str:
    if not path.exists():
        return f"<missing: {path}>"
    return path.read_text(errors="replace")


def compact_transcript(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": event.get("id"),
            "role": event.get("role"),
            "message": event.get("message"),
        }
        for event in transcript.get("events", [])
    ]


def render_prompt(evaluation_payload: dict[str, Any]) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text()
    return template.replace(
        "{{EVALUATION_PAYLOAD}}",
        json.dumps(evaluation_payload, indent=2),
    )


def build_messages(
    shortlist_json: str,
    commute_csv: str,
    shortlist_md: str,
    transcript: dict[str, Any],
) -> list[dict[str, str]]:
    evaluation_payload = {
        "artifacts": {
            "/app/apartment_shortlist.json": shortlist_json,
            "/app/apartment_commute_analysis.csv": commute_csv,
            "/app/apartment_shortlist.md": shortlist_md,
        },
        "transcript": compact_transcript(transcript),
    }
    prompt = render_prompt(evaluation_payload)

    return [
        {
            "role": "system",
            "content": (
                "You are an impartial LLM judge for an AI-agent evaluation. "
                "Return only valid JSON. Do not include Markdown."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]


def ask_openrouter(config: Config, messages: list[dict[str, str]]) -> str:
    response = post_json(
        OPENROUTER_URL,
        {
            "model": config.model,
            "messages": messages,
        },
        headers={"Authorization": f"Bearer {config.api_key}"},
    )
    message = response["choices"][0]["message"]["content"]
    if not isinstance(message, str) or not message.strip():
        raise ValueError("OpenRouter response must be a non-empty string")
    return message.strip()


def parse_judgment(message: str) -> dict[str, Any]:
    try:
        judgment = json.loads(message)
    except json.JSONDecodeError:
        start = message.find("{")
        end = message.rfind("}")
        if start < 0 or end < start:
            raise
        judgment = json.loads(message[start : end + 1])

    if not isinstance(judgment, dict):
        raise ValueError("LLM judge response must be a JSON object")
    score = judgment.get("score")
    if not isinstance(score, int | float):
        raise ValueError("LLM judge response must contain a numeric score field")
    judgment["score"] = max(0.0, min(1.0, float(score)))
    return judgment


def write_judge_log(judgment: dict[str, Any]) -> None:
    JUDGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    JUDGE_LOG_PATH.write_text(json.dumps(judgment, indent=2) + "\n")


def main() -> int:
    config = Config(
        model=os.environ.get("MODEL_NAME", "openai/gpt-5.2"),
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    shortlist_json = read_artifact(SHORTLIST_JSON_PATH)
    commute_csv = read_artifact(COMMUTE_CSV_PATH)
    shortlist_md = read_artifact(SHORTLIST_MD_PATH)
    transcript = read_transcript()

    messages = build_messages(
        shortlist_json,
        commute_csv,
        shortlist_md,
        transcript,
    )
    raw_judgment = ask_openrouter(config, messages)
    judgment = parse_judgment(raw_judgment)
    write_judge_log(judgment)

    print(json.dumps(judgment, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        failure = {
            "score": 0.0,
            "reason": f"LLM judge failed to run: {exc}",
            "subscores": {},
            "strengths": [],
            "problems": [type(exc).__name__],
            "recommended_score_explanation": "The judge failed before producing a valid score.",
        }
        write_judge_log(failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        raise SystemExit(1)
