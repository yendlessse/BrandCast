"""RACOI 공개 데이터 원본 수집 모듈.

원본 Excel/JSON은 `데이터/원본`에 보존하고, 수집 이력은 JSONL로 남긴다.
분석용 행 테이블 적재는 이 모듈의 범위가 아니라 다음 DB 이슈에서 수행한다.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, unquote
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_BASE_URL = "https://www.racoi.or.kr"
TIMEOUT_SECONDS = 30
SOURCE_FOLDERS = {
    "internet_response_weekly": "인터넷반응_주간",
    "total_response_monthly": "종합반응_월간",
    "comment_analysis": "댓글반응_상세",
}
COMMENT_ENDPOINTS = {
    "comments_rank": "getCommentsTable",
    "positive_comments_rank": "getPositiveCommentsTable",
    "sentiment_trend": "getTrendLineChart",
    "sentiment_distribution": "getTrendDoughnutChart",
    "wordcloud": "getWordCloudChart",
    "network_rank": "getNetworkTable",
    "network_edges": "getNetworkSource",
    "network_nodes": "getNetworkChart",
}


class RacoiCollectionError(RuntimeError):
    """RACOI 응답이 수집 가능한 원본 형식이 아닐 때 발생한다."""


@dataclass
class CollectionResult:
    source_name: str
    dataset_name: str
    collection_status: str
    source_url: str
    collected_at: str
    period_start: str | None
    period_end: str | None
    request_pjseq: int | None
    request_nweek: str | None
    http_status: int | None
    content_type: str | None
    response_format: str | None
    checksum: str | None
    file_path: str | None
    byte_count: int | None
    row_count: int | None
    structure_summary: dict[str, Any] | None
    error_message: str | None = None


def create_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "BrandCast-RACOI-Collector/1.0"})
    return session


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("_")


def _all_genre_filters() -> str:
    return json.dumps(
        [{"catId": f"cat00{number}", "isAll": True, "dayPatterns": []} for number in range(1, 5)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def detect_response_format(content: bytes) -> str:
    stripped = content.lstrip()
    if content.startswith(b"PK\x03\x04"):
        return "xlsx"
    if stripped.startswith((b"{", b"[")):
        return "json"
    if stripped.lower().startswith((b"<!doctype html", b"<html")):
        return "html"
    return "unknown"


def inspect_json(content: bytes) -> tuple[int | None, dict[str, Any]]:
    value = json.loads(content.decode("utf-8-sig"))
    if isinstance(value, list):
        keys = sorted({key for item in value if isinstance(item, dict) for key in item})
        return len(value), {"top_level": "list", "fields": keys}
    if isinstance(value, dict):
        return None, {"top_level": "object", "fields": sorted(value)}
    return None, {"top_level": type(value).__name__}


def inspect_xlsx(content: bytes) -> tuple[int | None, dict[str, Any]]:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(BytesIO(content)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = []
        total_rows = 0
        for index, sheet in enumerate(workbook.findall("main:sheets/main:sheet", namespace), start=1):
            xml_path = f"xl/worksheets/sheet{index}.xml"
            root = ElementTree.fromstring(archive.read(xml_path))
            rows = len(root.findall(".//main:sheetData/main:row", namespace))
            merges = len(root.findall(".//main:mergeCells/main:mergeCell", namespace))
            total_rows += rows
            sheets.append({"name": sheet.attrib.get("name"), "worksheet": xml_path, "physical_row_count": rows, "merged_cell_count": merges})
    return total_rows, {"workbook_sheet_count": len(sheets), "sheets": sheets}


class RacoiCollector:
    def __init__(self, project_root: Path, base_url: str = DEFAULT_BASE_URL, session: requests.Session | None = None) -> None:
        self.project_root = Path(project_root)
        self.base_url = base_url.rstrip("/") + "/"
        self.session = session or create_session()
        self.raw_root = self.project_root / "데이터" / "원본"
        self.metadata_path = self.raw_root / "수집_메타데이터.jsonl"

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _metadata_rows(self) -> list[dict[str, Any]]:
        if not self.metadata_path.exists():
            return []
        rows = []
        for line in self.metadata_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _append_metadata(self, result: CollectionResult) -> None:
        self.raw_root.mkdir(parents=True, exist_ok=True)
        with self.metadata_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    def _failure(self, source_name: str, dataset_name: str, source_url: str, period: str | None, pjseq: int | None, nweek: str | None, response: requests.Response | None, error: Exception | str) -> CollectionResult:
        result = CollectionResult(source_name, dataset_name, "failed", source_url, _now(), period, period, pjseq, nweek, response.status_code if response else None, response.headers.get("Content-Type") if response else None, None, None, None, None, None, None, str(error))
        self._append_metadata(result)
        return result

    def _save(self, source_name: str, dataset_name: str, source_url: str, period: str | None, pjseq: int | None, nweek: str | None, response: requests.Response) -> CollectionResult:
        content = response.content
        response_format = detect_response_format(content)
        if not content:
            raise RacoiCollectionError("응답 본문이 비어 있습니다.")
        if response_format == "html":
            raise RacoiCollectionError("HTML 응답입니다. 로그인/오류 페이지 여부를 확인하세요.")
        if response_format == "unknown":
            raise RacoiCollectionError("Excel 또는 JSON 형식이 아닌 응답입니다.")
        row_count, structure = inspect_xlsx(content) if response_format == "xlsx" else inspect_json(content)
        checksum = hashlib.sha256(content).hexdigest()
        existing = next((row for row in self._metadata_rows() if row.get("collection_status") == "success" and row.get("source_name") == source_name and row.get("dataset_name") == dataset_name and row.get("checksum") == checksum and row.get("file_path")), None)
        if existing:
            result = CollectionResult(source_name, dataset_name, "duplicate", source_url, _now(), period, period, pjseq, nweek, response.status_code, response.headers.get("Content-Type"), response_format, checksum, existing["file_path"], len(content), row_count, structure)
            self._append_metadata(result)
            return result
        extension = "xlsx" if response_format == "xlsx" else "json"
        folder = self.raw_root / SOURCE_FOLDERS[source_name]
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{_safe_name(dataset_name)}_{checksum[:12]}.{extension}"
        target = folder / name
        target.write_bytes(content)
        result = CollectionResult(source_name, dataset_name, "success", source_url, _now(), period, period, pjseq, nweek, response.status_code, response.headers.get("Content-Type"), response_format, checksum, str(target.relative_to(self.project_root)), len(content), row_count, structure)
        self._append_metadata(result)
        return result

    def _post_api(self, path: str, payload: dict[str, Any]) -> requests.Response:
        response = self.session.post(self._url(path), data={"param": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response

    def latest_periods(self, year: int | None = None) -> dict[str, Any]:
        response = self._post_api("/kobaco/select/report.getLastWeekNMonth.do", {"ordstr": "dfm", "year": year or datetime.now().year})
        data = response.json()
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or not data.get("dfm") or not data.get("mdfm"):
            raise RacoiCollectionError("최신 주간/월간 기간 응답에 필요한 코드가 없습니다.")
        return data

    def _download_excel(self, source_name: str, dataset_name: str, rtype: str, period: str) -> CollectionResult:
        url = self._url("/kobaco/excel/mexceldown.do")
        payload = {"rtype": rtype, "st": period, "ed": period, "datep_st": period, "datep_ed": period, "filterConditions": _all_genre_filters()}
        response: requests.Response | None = None
        try:
            response = self.session.post(url, data=payload, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return self._save(source_name, dataset_name, url, period, None, None, response)
        except (requests.RequestException, RacoiCollectionError, ValueError, zipfile.BadZipFile) as error:
            return self._failure(source_name, dataset_name, url, period, None, None, response, error)

    def download_weekly_internet_response(self, week_code: str) -> CollectionResult:
        return self._download_excel("internet_response_weekly", f"인터넷반응DB_{week_code}", "1", week_code)

    def download_monthly_total_response(self, month_code: str) -> CollectionResult:
        return self._download_excel("total_response_monthly", f"종합반응DB_{month_code}", "2", month_code)

    def latest_comment_week(self, pjseq: int) -> str:
        latest = self._post_api("/kobaco/select/report.getLatestCommentDate.do", {"pjseq": pjseq}).json()
        if isinstance(latest, list):
            latest = latest[0] if latest else None
        date = latest.get("date") if isinstance(latest, dict) else None
        if not date and isinstance(latest, dict):
            try:
                date = f"{int(latest['commentyear']):04d}{int(latest['commentmonth']):02d}{int(latest['commentday']):02d}"
            except (KeyError, TypeError, ValueError):
                date = None
        if not date:
            raise RacoiCollectionError("댓글 최신일자를 받지 못했습니다.")
        week = self._post_api("/kobaco/select/report.getWeekInfoByDate.do", {"date": date.replace("-", "")}).json()
        if isinstance(week, list):
            week = week[0] if week else None
        nweek = (week.get("nweek") or week.get("dfm")) if isinstance(week, dict) else None
        if not nweek:
            raise RacoiCollectionError("댓글 주차 코드를 받지 못했습니다.")
        return str(nweek)

    def download_comment_analysis(self, pjseq: int, nweek: str | None = None) -> list[CollectionResult]:
        nweek = nweek or self.latest_comment_week(pjseq)
        results = []
        for dataset_name, endpoint in COMMENT_ENDPOINTS.items():
            url = self._url(f"/kobaco/select/ott.{endpoint}.do")
            payload: dict[str, Any] = {"pjseq": pjseq, "nweek": nweek}
            if endpoint == "getTrendLineChart":
                payload["limit"] = 14
            response: requests.Response | None = None
            try:
                response = self._post_api(f"/kobaco/select/ott.{endpoint}.do", payload)
                results.append(self._save("comment_analysis", dataset_name, url, nweek, pjseq, nweek, response))
            except (requests.RequestException, RacoiCollectionError, ValueError, zipfile.BadZipFile) as error:
                results.append(self._failure("comment_analysis", dataset_name, url, nweek, pjseq, nweek, response, error))
            time.sleep(0.2)
        return results


def summarize_results(results: list[CollectionResult]) -> dict[str, int]:
    return {status: sum(result.collection_status == status for result in results) for status in ("success", "duplicate", "failed")}
