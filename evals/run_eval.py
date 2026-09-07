"""Harnais d'évaluation de l'agent.

Trois familles de contrôles, correspondant aux trois façons dont un agent
échoue en production :

1. **Exactitude** — la valeur citée correspond-elle à la vérité terrain,
   calculée par une requête de référence exécutée au moment du test ?
2. **Ancrage** — l'agent a-t-il réellement interrogé la base, ou a-t-il répondu
   de mémoire ? Un chiffre juste obtenu sans `run_sql` est un coup de chance,
   pas un comportement fiable.
3. **Refus** — sur une question hors périmètre, l'agent refuse-t-il au lieu
   d'inventer ?

Usage :
    python evals/run_eval.py                 # avec le vrai LLM
    python evals/run_eval.py --json out.json # export des métriques
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odoo_ai_agent.agent import OdooAgent  # noqa: E402
from odoo_ai_agent.config import Settings  # noqa: E402
from odoo_ai_agent.db import make_database  # noqa: E402
from odoo_ai_agent.llm import make_llm  # noqa: E402
from odoo_ai_agent.retriever import build_retriever  # noqa: E402

_NUMBER_RE = re.compile(r"-?\d[\d   .,]*")


@dataclass
class CaseResult:
    case_id: str
    question: str
    passed: bool
    reason: str
    expected: str | None
    answer: str
    used_sql: bool
    steps: int
    duration_s: float


def extract_numbers(text: str) -> list[float]:
    """Extrait les nombres d'une réponse en français (1 234,56 / 1234.56)."""
    values: list[float] = []
    for raw in _NUMBER_RE.findall(text):
        cleaned = raw.strip().replace(" ", "").replace(" ", "").replace(" ", "")
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        cleaned = cleaned.rstrip(".")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def ground_truth(db_path: Path, sql: str):  # noqa: ANN201
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(sql).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def check_case(case: dict, answer, db_path: Path) -> tuple[bool, str, str | None]:  # noqa: ANN001
    text = answer.text or ""

    if case.get("requires_sql") and not answer.used_database:
        return False, "aucune requête SQL exécutée (réponse non ancrée)", None

    if case.get("expect") == "refusal":
        needles = case.get("must_mention_any", [])
        lowered = text.lower()
        if any(n.lower() in lowered for n in needles):
            return True, "refus correctement exprimé", None
        return False, "l'agent aurait dû refuser de répondre", None

    expected = ground_truth(db_path, case["reference_sql"])

    if case.get("expect") == "text":
        ok = expected is not None and str(expected).lower() in text.lower()
        return ok, "valeur textuelle attendue absente" if not ok else "ok", str(expected)

    tolerance = float(case.get("tolerance", 0))
    numbers = extract_numbers(text)
    if not numbers:
        return False, "aucun nombre dans la réponse", str(expected)
    target = float(expected)
    margin = abs(target) * tolerance if tolerance else 0.5
    if any(abs(n - target) <= max(margin, 0.001) for n in numbers):
        return True, "ok", str(expected)
    return False, f"valeur attendue {target}, trouvée {numbers}", str(expected)


def run(settings: Settings, cases_path: Path) -> list[CaseResult]:
    cases = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    db_path = Path(settings.database_url.split("///", 1)[-1])

    results: list[CaseResult] = []
    for case in cases:
        database = make_database(settings.database_url, settings.max_rows, settings.query_timeout_s)
        agent = OdooAgent(
            llm=make_llm(settings.llm_provider, settings.llm_model, settings.temperature),
            database=database,
            retriever=build_retriever(settings.kb_path),
            settings=settings,
        )
        started = time.time()
        answer = agent.ask(case["question"])
        duration = round(time.time() - started, 2)
        passed, reason, expected = check_case(case, answer, db_path)
        database.close()
        results.append(
            CaseResult(
                case_id=case["id"],
                question=" ".join(case["question"].split()),
                passed=passed,
                reason=reason,
                expected=expected,
                answer=answer.text,
                used_sql=answer.used_database,
                steps=answer.steps,
                duration_s=duration,
            )
        )
        flag = "PASS" if passed else "FAIL"
        print(f"[{flag}] {case['id']:<24} {reason}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Évaluation de l'agent Odoo")
    parser.add_argument("--cases", default=str(Path(__file__).parent / "golden_questions.yaml"))
    parser.add_argument("--json", dest="json_out", help="Fichier de sortie des métriques")
    args = parser.parse_args()

    settings = Settings()
    results = run(settings, Path(args.cases))

    total = len(results)
    passed = sum(r.passed for r in results)
    grounded = sum(r.used_sql for r in results)
    avg_steps = round(sum(r.steps for r in results) / total, 2) if total else 0
    avg_time = round(sum(r.duration_s for r in results) / total, 2) if total else 0

    print("\n--- Métriques ---")
    print(f"Exactitude        : {passed}/{total} ({passed / total:.0%})")
    print(f"Réponses ancrées  : {grounded}/{total}")
    print(f"Étapes moyennes   : {avg_steps}")
    print(f"Latence moyenne   : {avg_time} s")

    if args.json_out:
        payload = {
            "summary": {
                "total": total,
                "passed": passed,
                "accuracy": round(passed / total, 4) if total else 0,
                "grounded": grounded,
                "avg_steps": avg_steps,
                "avg_duration_s": avg_time,
            },
            "cases": [asdict(r) for r in results],
        }
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nMétriques écrites dans {args.json_out}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
