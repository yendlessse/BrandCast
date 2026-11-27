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
    current = start
    while current <= end:
        iso_year, iso_week, _ = current.isocalendar()
        code = f"{iso_year}{iso_week:02d}"
        if code not in codes:
            codes.append(code)
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
    collector = RacoiCollector(PROJECT_ROOT, os.getenv("RACOI_BASE_URL", args.base_url))
    periods = collector.latest_periods()
    if args.start_date and args.end_date:
        start, end = _parse_date(args.start_date), _parse_date(args.end_date)
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        weekly_codes = _week_codes(start, end)
        monthly_codes = _month_codes(start, end)
    elif args.start_date or args.end_date:
        raise ValueError("기간 수집은 --start-date와 --end-date를 함께 지정해야 합니다.")
    else:
        weekly_codes = [str(periods["dfm"])]
        monthly_codes = [str(periods["mdfm"])]

    results = []
    for code in weekly_codes:
        results.append(collector.download_weekly_internet_response(code))
    for code in monthly_codes:
        results.append(collector.download_monthly_total_response(code))
    if not args.skip_comments:
        # 방송 반응 최신 주차와 댓글 최신 주차는 서로 다를 수 있다.
        results.extend(collector.download_comment_analysis(args.comment_pjseq))
    return results, {"latest_week": periods["dfm"], "latest_month": periods["mdfm"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="RACOI 공개 원본 수집 실행기")
    parser.add_argument("--start-date", help="수집 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="수집 종료일 (YYYY-MM-DD)")
    parser.add_argument("--comment-pjseq", type=int, default=DEFAULT_COMMENT_PJSEQ, help="RACOI 프로그램 식별자")
    parser.add_argument("--skip-comments", action="store_true", help="댓글반응 JSON 8종 수집을 건너뜁니다.")
    parser.add_argument("--probe", action="store_true", help="최신 1주·1개월·댓글 8종만 수집합니다(기본 동작과 동일).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="RACOI 기본 URL")
    args = parser.parse_args()
    try:
        results, periods = run(args)
    except (ValueError, RacoiCollectionError, OSError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    summary = summarize_results(results)
    print(json.dumps({"status": "completed" if not summary["failed"] else "completed_with_failures", "periods": periods, "summary": summary, "results": [result.__dict__ for result in results]}, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
