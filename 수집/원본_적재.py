"""RACOI 원본 파일을 수정하지 않고 MariaDB raw 테이블에 적재한다."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import mariadb
from dotenv import load_dotenv
from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "데이터" / "원본"
METADATA_PATH = RAW_ROOT / "수집_메타데이터.jsonl"
WEEKLY_COLUMNS = (
    "period_code program_name channel_name broadcast_day_text "
    "viewer_post_value viewer_comment_value viewer_video_view_value "
    "media_news_value media_video_value viewer_post_share_value "
    "viewer_comment_share_value viewer_video_view_share_value "
    "media_news_share_value media_video_share_value household_viewer_value "
    "viewer_2049_value household_rating_value rating_2049_value"
).split()
MONTHLY_COLUMNS = (
    "period_code program_name channel_name broadcast_day_text "
    "viewer_post_value viewer_comment_value viewer_video_view_value "
    "media_news_value media_video_value tv_household_viewer_value "
    "tv_individual_viewer_value tv_male_viewer_value tv_female_viewer_value "
    "tv_age10_viewer_value tv_age20_viewer_value tv_age30_viewer_value "
    "tv_age40_viewer_value tv_age50_viewer_value tv_household_rating_value "
    "tv_individual_rating_value tv_male_rating_value tv_female_rating_value "
    "tv_age10_rating_value tv_age20_rating_value tv_age30_rating_value "
    "tv_age40_rating_value tv_age50_rating_value tv_vod_value pc_live_value "
    "pc_vod_value mobile_live_value mobile_vod_value"
).split()


@dataclass(frozen=True)
class SourceFile:
    metadata: dict[str, Any]
    path: Path


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def read_metadata() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not METADATA_PATH.exists():
        return rows
    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _event_key(row: dict[str, Any]) -> str:
    payload = {
        key: row.get(key)
        for key in (
            "source_name", "dataset_name", "collection_status", "source_url", "collected_at",
            "period_start", "period_end", "request_pjseq", "request_nweek", "checksum", "file_path",
        )
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _source_path(row: dict[str, Any]) -> Path | None:
    value = row.get("file_path")
    if not value:
        return None
    path = PROJECT_ROOT / Path(str(value).replace("\\", "/"))
    return path if path.is_file() else None


def materialized_sources(rows: Iterable[dict[str, Any]], source_name: str, formats: set[str]) -> list[SourceFile]:
    """실제 파일이 있고 같은 내용 지문은 한 번만 적재할 원본을 선택한다."""
    selected: dict[tuple[str, str, str], SourceFile] = {}
    for row in rows:
        if row.get("source_name") != source_name or row.get("response_format") not in formats:
            continue
        if row.get("collection_status") not in {"success", "duplicate"}:
            continue
        path = _source_path(row)
        if path is None:
            continue
        summary = row.get("structure_summary") or {}
        fingerprint = summary.get("content_fingerprint") or row.get("checksum")
        key = (str(row.get("dataset_name")), str(fingerprint), str(row.get("response_format")))
        selected.setdefault(key, SourceFile(row, path))
    return list(selected.values())


def connect() -> mariadb.Connection:
    load_dotenv(PROJECT_ROOT / ".env")
    password = os.getenv("MARIADB_PASSWORD")
    if not password:
        raise RuntimeError("MARIADB_PASSWORD 환경 변수가 필요합니다. .env를 확인하세요.")
    return mariadb.connect(
        host=os.getenv("MARIADB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARIADB_PORT", "3307")),
        user=os.getenv("MARIADB_USER", "brandcast_user"),
        password=password,
        database=os.getenv("MARIADB_DATABASE", "brandcast"),
        autocommit=False,
    )


DDL = [
    """
    CREATE TABLE IF NOT EXISTS raw_ingestion_log (
        ingestion_run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_event_key CHAR(64) NOT NULL,
        source_name VARCHAR(80) NOT NULL,
        dataset_name VARCHAR(120) NOT NULL,
        collection_status VARCHAR(20) NOT NULL,
        source_url TEXT NULL,
        collected_at DATETIME NULL,
        period_start VARCHAR(16) NULL,
        period_end VARCHAR(16) NULL,
        request_pjseq BIGINT NULL,
        request_nweek VARCHAR(16) NULL,
        http_status SMALLINT NULL,
        content_type VARCHAR(255) NULL,
        response_format VARCHAR(20) NULL,
        checksum CHAR(64) NULL,
        content_fingerprint CHAR(64) NULL,
        file_path TEXT NULL,
        byte_count BIGINT NULL,
        row_count BIGINT NULL,
        structure_summary_json LONGTEXT NULL,
        error_message TEXT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ingestion_run_id),
        UNIQUE KEY uq_raw_ingestion_event (ingestion_event_key),
        KEY ix_raw_ingestion_source_period (source_name, period_start),
        CHECK (structure_summary_json IS NULL OR JSON_VALID(structure_summary_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_internet_response (
        raw_internet_response_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_run_id BIGINT UNSIGNED NOT NULL,
        source_checksum CHAR(64) NOT NULL,
        source_file_path TEXT NOT NULL,
        source_sheet_name VARCHAR(100) NOT NULL,
        source_row_number INT NOT NULL,
        period_code VARCHAR(16) NULL,
        program_name VARCHAR(255) NULL,
        channel_name VARCHAR(255) NULL,
        broadcast_day_text VARCHAR(100) NULL,
        viewer_post_value VARCHAR(100) NULL,
        viewer_comment_value VARCHAR(100) NULL,
        viewer_video_view_value VARCHAR(100) NULL,
        media_news_value VARCHAR(100) NULL,
        media_video_value VARCHAR(100) NULL,
        viewer_post_share_value VARCHAR(100) NULL,
        viewer_comment_share_value VARCHAR(100) NULL,
        viewer_video_view_share_value VARCHAR(100) NULL,
        media_news_share_value VARCHAR(100) NULL,
        media_video_share_value VARCHAR(100) NULL,
        household_viewer_value VARCHAR(100) NULL,
        viewer_2049_value VARCHAR(100) NULL,
        household_rating_value VARCHAR(100) NULL,
        rating_2049_value VARCHAR(100) NULL,
        raw_payload_json LONGTEXT NOT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (raw_internet_response_id),
        UNIQUE KEY uq_raw_internet_source_row (source_checksum, source_sheet_name, source_row_number),
        KEY ix_raw_internet_period_program (period_code, program_name),
        CONSTRAINT fk_raw_internet_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES raw_ingestion_log (ingestion_run_id),
        CHECK (JSON_VALID(raw_payload_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_total_response (
        raw_total_response_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_run_id BIGINT UNSIGNED NOT NULL,
        source_checksum CHAR(64) NOT NULL,
        source_file_path TEXT NOT NULL,
        source_sheet_name VARCHAR(100) NOT NULL,
        source_row_number INT NOT NULL,
        period_code VARCHAR(16) NULL,
        program_name VARCHAR(255) NULL,
        channel_name VARCHAR(255) NULL,
        broadcast_day_text VARCHAR(100) NULL,
        viewer_post_value VARCHAR(100) NULL,
        viewer_comment_value VARCHAR(100) NULL,
        viewer_video_view_value VARCHAR(100) NULL,
        media_news_value VARCHAR(100) NULL,
        media_video_value VARCHAR(100) NULL,
        tv_household_viewer_value VARCHAR(100) NULL,
        tv_individual_viewer_value VARCHAR(100) NULL,
        tv_male_viewer_value VARCHAR(100) NULL,
        tv_female_viewer_value VARCHAR(100) NULL,
        tv_age10_viewer_value VARCHAR(100) NULL,
        tv_age20_viewer_value VARCHAR(100) NULL,
        tv_age30_viewer_value VARCHAR(100) NULL,
        tv_age40_viewer_value VARCHAR(100) NULL,
        tv_age50_viewer_value VARCHAR(100) NULL,
        tv_household_rating_value VARCHAR(100) NULL,
        tv_individual_rating_value VARCHAR(100) NULL,
        tv_male_rating_value VARCHAR(100) NULL,
        tv_female_rating_value VARCHAR(100) NULL,
        tv_age10_rating_value VARCHAR(100) NULL,
        tv_age20_rating_value VARCHAR(100) NULL,
        tv_age30_rating_value VARCHAR(100) NULL,
        tv_age40_rating_value VARCHAR(100) NULL,
        tv_age50_rating_value VARCHAR(100) NULL,
        tv_vod_value VARCHAR(100) NULL,
        pc_live_value VARCHAR(100) NULL,
        pc_vod_value VARCHAR(100) NULL,
        mobile_live_value VARCHAR(100) NULL,
        mobile_vod_value VARCHAR(100) NULL,
        raw_payload_json LONGTEXT NOT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (raw_total_response_id),
        UNIQUE KEY uq_raw_total_source_row (source_checksum, source_sheet_name, source_row_number),
        KEY ix_raw_total_period_program (period_code, program_name),
        CONSTRAINT fk_raw_total_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES raw_ingestion_log (ingestion_run_id),
        CHECK (JSON_VALID(raw_payload_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_comment_keyword (
        raw_comment_keyword_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_run_id BIGINT UNSIGNED NOT NULL,
        source_checksum CHAR(64) NOT NULL,
        source_file_path TEXT NOT NULL,
        dataset_name VARCHAR(80) NOT NULL,
        source_array_index INT NOT NULL,
        request_pjseq BIGINT NULL,
        request_nweek VARCHAR(16) NULL,
        response_nweek VARCHAR(16) NULL,
        rank_value INT NULL,
        keyword_text VARCHAR(500) NULL,
        frequency_value VARCHAR(100) NULL,
        sentiment_type_code VARCHAR(20) NULL,
        raw_payload_json LONGTEXT NOT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (raw_comment_keyword_id),
        UNIQUE KEY uq_raw_keyword_source_row (source_checksum, dataset_name, source_array_index),
        CONSTRAINT fk_raw_keyword_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES raw_ingestion_log (ingestion_run_id),
        CHECK (JSON_VALID(raw_payload_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_comment_sentiment (
        raw_comment_sentiment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_run_id BIGINT UNSIGNED NOT NULL,
        source_checksum CHAR(64) NOT NULL,
        source_file_path TEXT NOT NULL,
        dataset_name VARCHAR(80) NOT NULL,
        source_array_index INT NOT NULL,
        request_pjseq BIGINT NULL,
        request_nweek VARCHAR(16) NULL,
        response_nweek VARCHAR(16) NULL,
        positive_score_value VARCHAR(100) NULL,
        negative_score_value VARCHAR(100) NULL,
        raw_payload_json LONGTEXT NOT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (raw_comment_sentiment_id),
        UNIQUE KEY uq_raw_sentiment_source_row (source_checksum, dataset_name, source_array_index),
        CONSTRAINT fk_raw_sentiment_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES raw_ingestion_log (ingestion_run_id),
        CHECK (JSON_VALID(raw_payload_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_comment_network (
        raw_comment_network_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ingestion_run_id BIGINT UNSIGNED NOT NULL,
        source_checksum CHAR(64) NOT NULL,
        source_file_path TEXT NOT NULL,
        dataset_name VARCHAR(80) NOT NULL,
        source_array_index INT NOT NULL,
        request_pjseq BIGINT NULL,
        request_nweek VARCHAR(16) NULL,
        rank_value INT NULL,
        source_keyword VARCHAR(500) NULL,
        target_keyword VARCHAR(500) NULL,
        frequency_value VARCHAR(100) NULL,
        raw_payload_json LONGTEXT NOT NULL,
        loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (raw_comment_network_id),
        UNIQUE KEY uq_raw_network_source_row (source_checksum, dataset_name, source_array_index),
        CONSTRAINT fk_raw_network_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES raw_ingestion_log (ingestion_run_id),
        CHECK (JSON_VALID(raw_payload_json))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def ensure_schema(connection: mariadb.Connection) -> None:
    cursor = connection.cursor()
    for statement in DDL:
        cursor.execute(statement)
    connection.commit()


def _insert_ingestion_log(connection: mariadb.Connection, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    sql = """
    INSERT IGNORE INTO raw_ingestion_log (
        ingestion_event_key, source_name, dataset_name, collection_status, source_url, collected_at,
        period_start, period_end, request_pjseq, request_nweek, http_status, content_type,
        response_format, checksum, content_fingerprint, file_path, byte_count, row_count,
        structure_summary_json, error_message
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor = connection.cursor()
    for row in rows:
        summary = row.get("structure_summary") or {}
        cursor.execute(sql, (
            _event_key(row), row.get("source_name"), row.get("dataset_name"), row.get("collection_status"),
            row.get("source_url"), row.get("collected_at", "").replace("T", " ").split("+")[0] or None,
            row.get("period_start"), row.get("period_end"), row.get("request_pjseq"), row.get("request_nweek"),
            row.get("http_status"), row.get("content_type"), row.get("response_format"), row.get("checksum"),
            summary.get("content_fingerprint"), row.get("file_path"), row.get("byte_count"), row.get("row_count"),
            json.dumps(summary, ensure_ascii=False), row.get("error_message"),
        ))
    connection.commit()
    cursor.execute("SELECT ingestion_event_key, ingestion_run_id FROM raw_ingestion_log")
    return {event_key: int(run_id) for event_key, run_id in cursor.fetchall()}


def _actual_rows(path: Path, header_rows: int) -> tuple[str, list[tuple[int, tuple[Any, ...]]]]:
    workbook = load_workbook(path, read_only=False, data_only=False)
    worksheet = workbook.active
    values: list[tuple[int, tuple[Any, ...]]] = []
    for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if row_number <= header_rows or not any(value is not None for value in row):
            continue
        values.append((row_number, row))
    sheet_name = worksheet.title
    workbook.close()
    return sheet_name, values


def _insert_excel(
    connection: mariadb.Connection,
    table: str,
    sources: Iterable[SourceFile],
    ingestion_ids: dict[str, int],
    header_rows: int,
    columns: list[str],
) -> dict[str, int]:
    field_names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in range(5 + len(columns) + 1))
    sql = f"""
    INSERT IGNORE INTO {table} (
        ingestion_run_id, source_checksum, source_file_path, source_sheet_name, source_row_number,
        {field_names}, raw_payload_json
    ) VALUES ({placeholders})
    """
    inserted = 0
    scanned = 0
    cursor = connection.cursor()
    for source in sources:
        metadata = source.metadata
        checksum = metadata.get("checksum")
        if not checksum:
            continue
        sheet_name, rows = _actual_rows(source.path, header_rows)
        if not rows:
            continue
        ingestion_id = ingestion_ids[_event_key(metadata)]
        for row_number, values in rows:
            mapped = [_value(values[index]) if index < len(values) else None for index in range(len(columns))]
            payload = json.dumps({column: mapped[index] for index, column in enumerate(columns)}, ensure_ascii=False)
            cursor.execute(sql, (ingestion_id, checksum, source.path.relative_to(PROJECT_ROOT).as_posix(), sheet_name, row_number, *mapped, payload))
            inserted += cursor.rowcount
            scanned += 1
        connection.commit()
    return {"scanned": scanned, "inserted": inserted}


def _insert_comments(connection: mariadb.Connection, sources: Iterable[SourceFile], ingestion_ids: dict[str, int]) -> dict[str, int]:
    statements = {
        "keyword": """INSERT IGNORE INTO raw_comment_keyword (ingestion_run_id, source_checksum, source_file_path, dataset_name, source_array_index, request_pjseq, request_nweek, response_nweek, rank_value, keyword_text, frequency_value, sentiment_type_code, raw_payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        "sentiment": """INSERT IGNORE INTO raw_comment_sentiment (ingestion_run_id, source_checksum, source_file_path, dataset_name, source_array_index, request_pjseq, request_nweek, response_nweek, positive_score_value, negative_score_value, raw_payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        "network": """INSERT IGNORE INTO raw_comment_network (ingestion_run_id, source_checksum, source_file_path, dataset_name, source_array_index, request_pjseq, request_nweek, rank_value, source_keyword, target_keyword, frequency_value, raw_payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    }
    keyword_sets = {"comments_rank", "positive_comments_rank", "wordcloud"}
    sentiment_sets = {"sentiment_trend", "sentiment_distribution"}
    inserted = {"keyword": 0, "sentiment": 0, "network": 0}
    cursor = connection.cursor()
    for source in sources:
        metadata = source.metadata
        try:
            records = json.loads(source.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(records, list):
            continue
        category = "keyword" if metadata.get("dataset_name") in keyword_sets else "sentiment" if metadata.get("dataset_name") in sentiment_sets else "network"
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            base = (
                ingestion_ids[_event_key(metadata)], metadata.get("checksum"),
                source.path.relative_to(PROJECT_ROOT).as_posix(), metadata.get("dataset_name"), index,
                metadata.get("request_pjseq"), metadata.get("request_nweek"),
            )
            payload = json.dumps(record, ensure_ascii=False)
            if category == "keyword":
                values = base + (_value(record.get("nweek")), record.get("rk1"), _value(record.get("keyword")), _value(record.get("frequency")), _value(record.get("sentimenttypecode")), payload)
            elif category == "sentiment":
                values = base + (_value(record.get("nweek")), _value(record.get("positivescore")), _value(record.get("negativescore")), payload)
            else:
                values = base + (record.get("rk1"), _value(record.get("bigram")), _value(record.get("target")), _value(record.get("frequency")), payload)
            cursor.execute(statements[category], values)
            inserted[category] += cursor.rowcount
        connection.commit()
    return inserted


def load_raw(connection: mariadb.Connection) -> dict[str, Any]:
    """수집 이력과 실제 존재하는 원본 파일을 raw 테이블로 적재한다."""
    rows = read_metadata()
    ensure_schema(connection)
    ingestion_ids = _insert_ingestion_log(connection, rows)
    weekly = materialized_sources(rows, "internet_response_weekly", {"xlsx"})
    monthly = materialized_sources(rows, "total_response_monthly", {"xlsx"})
    comments = materialized_sources(rows, "comment_analysis", {"json"})
    return {
        "ingestion_events": len(ingestion_ids),
        "weekly_files": len(weekly),
        "monthly_files": len(monthly),
        "comment_files": len(comments),
        "raw_internet_response": _insert_excel(connection, "raw_internet_response", weekly, ingestion_ids, 7, WEEKLY_COLUMNS),
        "raw_total_response": _insert_excel(connection, "raw_total_response", monthly, ingestion_ids, 8, MONTHLY_COLUMNS),
        "raw_comments": _insert_comments(connection, comments, ingestion_ids),
    }


def table_counts(connection: mariadb.Connection) -> dict[str, int]:
    cursor = connection.cursor()
    names = ["raw_ingestion_log", "raw_internet_response", "raw_total_response", "raw_comment_keyword", "raw_comment_sentiment", "raw_comment_network"]
    result: dict[str, int] = {}
    for name in names:
        cursor.execute(f"SELECT COUNT(*) FROM {name}")
        result[name] = int(cursor.fetchone()[0])
    return result
