#!/usr/bin/env python3
"""BrandCast 저장소 규칙 자동 검사.

`AGENTS.md`와 `문서/검증_체크리스트.md`의 규칙 중 파일 내용만 읽어 판정할 수 있는
항목을 검사한다. 노트북 실행, SQL 결과 대조, 그래프와 표의 값 일치 확인은 이 스크립트의
범위가 아니며 검증 에이전트가 로컬 MariaDB 환경에서 수행한다.

종료 코드
    0  오류 없음
    1  오류 1건 이상
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Q1~Q6 질문 노트북. 계획된 그래프 2개 규칙과 SQL 셀 규칙을 적용한다.
QUESTION_PREFIXES = ("03_", "04_", "05_", "06_", "07_", "08_")

# SQL 블록 상단 주석에 반드시 들어가야 하는 항목.
SQL_HEADER_KEYS = ("목적", "입력", "출력 단위", "분석 기간", "NULL")

# Python에서 집계·파생·순위를 다시 계산하는 호출. 도구 경계 조항 위반으로 본다.
FORBIDDEN_PY = (
    ".groupby(",
    ".merge(",
    ".pivot_table(",
    ".pct_change(",
    ".rolling(",
    ".cumsum(",
    "polyfit(",
    ".nlargest(",
    ".nsmallest(",
)

# 표시 목적일 수 있으나 SQL에서 처리했어야 하는 호출. 경고로만 보고한다.
WARN_PY = (".sort_values(", ".quantile(", ".corr(", ".rank(")

SECRET_PATTERNS = (
    re.compile(r"(mysql|mariadb)(\+\w+)?://[^\s'\"]*:[^\s'\"]+@"),
    re.compile(r"(?i)password\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*=\s*['\"][^'\"]{8,}['\"]"),
)

HANGUL = re.compile(r"[가-힣]")

errors: list[str] = []
warnings: list[str] = []
notes: list[str] = []


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [p for p in result.stdout.split("\0") if p]


def check_repository_hygiene(paths: list[str]) -> None:
    """원본 데이터와 비밀 설정이 커밋되지 않았는지, 금지된 폴더가 없는지 확인한다."""
    for path in paths:
        if path.startswith(".env") and path != ".env.example":
            errors.append(f"비밀 설정 파일이 커밋되었습니다: {path}")
        if path.startswith("데이터/원본/") and not path.endswith(".gitkeep"):
            errors.append(f"수집 원본이 커밋되었습니다: {path}")
        if path.startswith("데이터/임시/") or path.startswith("데이터/중간/"):
            errors.append(f"중간 데이터가 커밋되었습니다: {path}")
        if path.startswith("SQL/"):
            errors.append(f"별도 SQL/ 폴더를 두지 않는 규칙을 위반했습니다: {path}")
        if path.endswith(".csv") and "키워드" in path:
            errors.append(
                f"키워드 사전은 CSV가 아니라 Q4 노트북의 MariaDB 테이블로 관리합니다: {path}"
            )
        if "댓글_원문" in path:
            errors.append(f"원문 댓글이 커밋되었습니다: {path}")


def cell_text(cell: dict) -> str:
    source = cell.get("source", "")
    return source if isinstance(source, str) else "".join(source)


def output_text(cell: dict) -> str:
    chunks = []
    for output in cell.get("outputs", []) or []:
        for key in ("text",):
            value = output.get(key)
            if value:
                chunks.append(value if isinstance(value, str) else "".join(value))
        data = output.get("data", {}) or {}
        for key, value in data.items():
            if key.startswith("text/"):
                chunks.append(value if isinstance(value, str) else "".join(value))
    return "\n".join(chunks)


def check_sql_cell(name: str, index: int, text: str) -> None:
    """SQL 셀 상단 주석에 목적·입력·출력 단위·기간·NULL 기준이 있는지 확인한다."""
    header = "\n".join(text.splitlines()[:20])
    missing = [key for key in SQL_HEADER_KEYS if key not in header]
    if missing:
        errors.append(
            f"{name} 셀 {index}: SQL 상단 주석에 {', '.join(missing)} 항목이 없습니다."
        )
    comments = [line for line in text.splitlines() if line.lstrip().startswith("--")]
    if not comments:
        errors.append(f"{name} 셀 {index}: SQL 셀에 한국어 주석이 없습니다.")
    elif not any(HANGUL.search(line) for line in comments):
        errors.append(f"{name} 셀 {index}: SQL 주석이 한국어로 작성되지 않았습니다.")


def check_notebook(path: Path) -> None:
    name = path.name
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{name}: 노트북을 읽을 수 없습니다 ({error}).")
        return

    cells = document.get("cells", [])
    if not cells:
        errors.append(f"{name}: 셀이 없습니다.")
        return

    # 첫 셀은 대제목 표지, 둘째 셀은 핵심 질문 카드여야 한다.
    # 디자인 가이드의 표지·질문 카드는 HTML로 작성하므로 Markdown 제목과 HTML 제목을 모두 허용한다.
    first = cells[0]
    first_text = cell_text(first).lstrip()
    if first.get("cell_type") != "markdown" or not (
        first_text.startswith("# ") or "<h1" in first_text
    ):
        errors.append(f"{name}: 첫 번째 셀이 대제목 표지가 아닙니다.")
    if len(cells) < 2:
        errors.append(f"{name}: 핵심 질문 셀이 없습니다.")
    else:
        second = cells[1]
        second_text = cell_text(second)
        if second.get("cell_type") != "markdown" or not (
            "핵심 질문" in second_text or "CORE QUESTION" in second_text.upper()
        ):
            errors.append(f"{name}: 두 번째 셀이 핵심 질문 카드가 아닙니다.")

    code_cells = [
        (index, cell_text(cell), cell)
        for index, cell in enumerate(cells, start=1)
        if cell.get("cell_type") == "code"
    ]
    sql_cells = [
        (index, text)
        for index, text, _ in code_cells
        if text.lstrip().startswith(("%%sql", "%sql"))
    ]

    for index, text in sql_cells:
        check_sql_cell(name, index, text)

    for index, text, cell in code_cells:
        if text.lstrip().startswith(("%%sql", "%sql")):
            continue
        for pattern in FORBIDDEN_PY:
            if pattern in text:
                errors.append(
                    f"{name} 셀 {index}: Python에서 분석을 다시 계산하는 호출 {pattern} 이"
                    " 있습니다. 집계·파생·순위는 SQL에서 계산합니다."
                )
        for pattern in WARN_PY:
            if pattern in text:
                warnings.append(
                    f"{name} 셀 {index}: {pattern} 호출이 있습니다."
                    " SQL 결과를 그대로 쓰는지 확인이 필요합니다."
                )
        for regex in SECRET_PATTERNS:
            if regex.search(text):
                errors.append(f"{name} 셀 {index}: 접속 정보나 비밀값이 하드코딩되었습니다.")
        rendered = output_text(cell)
        for regex in SECRET_PATTERNS:
            if regex.search(rendered):
                errors.append(f"{name} 셀 {index}: 셀 출력에 비밀값이 남아 있습니다.")

    # 구현 전 스텁은 이후 규칙 검사를 생략한다.
    if len(cells) <= 2:
        notes.append(f"{name}: 셀 {len(cells)}개로 아직 구현 전입니다. 내용 검사를 건너뜁니다.")
        return

    if not name.startswith(QUESTION_PREFIXES):
        return

    if not sql_cells:
        errors.append(f"{name}: 질문 노트북에 SQL 셀이 없습니다.")

    saves = []
    for _, text, _ in code_cells:
        saves.extend(re.findall(r"savefig\(\s*[^)]*", text))
    if len(saves) != 2:
        errors.append(
            f"{name}: 계획된 그래프는 2개여야 합니다. savefig 호출 {len(saves)}개가 있습니다."
        )
    for call in saves:
        if "그래프/Q" not in call:
            warnings.append(
                f"{name}: 그래프 저장 경로가 질문별 폴더(그래프/Q*)인지 확인이 필요합니다: {call.strip()}"
            )


def main() -> int:
    paths = tracked_files()
    check_repository_hygiene(paths)

    # 추적 중인 노트북만 검사한다. .venv 같은 비추적 폴더를 훑지 않기 위한 선택이다.
    notebooks = sorted(
        ROOT / path
        for path in paths
        if path.endswith(".ipynb") and ".ipynb_checkpoints" not in path
    )
    for path in notebooks:
        check_notebook(path)

    print(f"검사한 노트북: {len(notebooks)}개, 추적 파일: {len(paths)}개")
    for note in notes:
        print(f"  정보  {note}")
    for warning in warnings:
        print(f"  경고  {warning}")
    for error in errors:
        print(f"  오류  {error}")
    print(f"\n오류 {len(errors)}건, 경고 {len(warnings)}건")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
