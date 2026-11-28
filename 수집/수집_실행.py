"""RACOI 원본 수집 실행기.

기본 실행은 최신 주간 인터넷반응, 최신 월간 종합반응, 댓글반응 8종을 한 번씩 수집한다.
원본 파일과 수집 메타데이터는 Git 추적 대상이 아닌 `데이터/원본`에 남는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from RACOI_자료_내려받기 import DEFAULT_BASE_URL, RacoiCollector, RacoiCollectionError, summarize_results


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMENT_PJSEQ = 11487


def _read_dotenv() -> None:
    """선택적 .env를 읽되, 이미 지정한 환경변수는 덮어쓰지 않는다."""
    dotenv = PROJECT_ROOT / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _week_codes(start: date, end: date) -> list[str]:
    codes = []
    current = start - timedelta(days=start.weekday())
    while current <= end:
        iso_year, iso_week, _ = current.isocalendar()
        codes.append(f"{iso_year}{iso_week:02d}")
        current += timedelta(days=7)
    return codes


def _month_codes(start: date, end: date) -> list[str]:
    codes = []
    current = start.replace(day=1)
    last = end.replace(day=1)
    while current <= last:
        codes.append(current.strftime("%Y%m"))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return codes


def run(args: argparse.Namespace) -> tuple[list, dict]:
    _read_dotenv()
    collector = RacoiCollector(PROJECT_ROOT, os.getenv("RACOI_BASE_URL") or args.base_url)
    periods = collector.latest_periods()
    latest_week, latest_month = str(periods["dfm"]), str(periods["mdfm"])
    start_value = args.start_date or os.getenv("DATA_START_DATE") or None
    end_value = args.end_date or os.getenv("DATA_END_DATE") or None
    if bool(start_value) != bool(end_value):
        raise ValueError("기간 수집은 시작일과 종료일을 함께 지정해야 합니다.")
    if args.probe or not start_value:
        weekly_codes = [latest_week]
        monthly_codes = [latest_month]
        mode = "probe"
    else:
        start, end = _parse_date(start_value), _parse_date(end_value or "")
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        weekly_codes = [code for code in _week_codes(start, end) if code <= latest_week]
        monthly_codes = [code for code in _month_codes(start, end) if code <= latest_month]
        if not weekly_codes and not monthly_codes:
            raise ValueError("최신 완료 주차·월 안에 수집할 기간이 없습니다.")
        mode = "range"

    results = []
    for code in weekly_codes:
        results.append(collector.download_weekly_internet_response(code))
    for code in monthly_codes:
        results.append(collector.download_monthly_total_response(code))
    if not args.skip_comments:
        # 방송 반응 최신 주차와 댓글 최신 주차는 서로 다를 수 있다.
        results.extend(collector.download_comment_analysis(args.comment_pjseq))
    return results, {
        "mode": mode,
        "requested_start_date": start_value,
        "requested_end_date": end_value,
        "latest_week": latest_week,
        "latest_month": latest_month,
        "weekly_codes": weekly_codes,
        "monthly_codes": monthly_codes,
        "comment_pjseq": None if args.skip_comments else args.comment_pjseq,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RACOI 공개 원본 수집 실행기")
    parser.add_argument("--start-date", help="수집 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="수집 종료일 (YYYY-MM-DD)")
    parser.add_argument("--comment-pjseq", type=int, default=DEFAULT_COMMENT_PJSEQ, help="RACOI 프로그램 식별자")
    parser.add_argument("--skip-comments", action="store_true", help="댓글반응 JSON 8종 수집을 건너뜁니다.")
    parser.add_argument("--probe", action="store_true", help="기간 설정과 무관하게 최신 1주·1개월·댓글 8종만 수집합니다.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="RACOI 기본 URL")
    args = parser.parse_args()
    try:
        results, execution = run(args)
    except (ValueError, RacoiCollectionError, OSError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    summary = summarize_results(results)
    print(json.dumps({"status": "completed" if not summary["failed"] else "completed_with_failures", "execution": execution, "summary": summary, "results": [result.__dict__ for result in results]}, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
