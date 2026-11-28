# 이슈 5 분석용 테이블 ERD

> raw 원본은 수정하지 않고, 이 문서의 분석 테이블은 `노트북/02_데이터_적재_품질_및_전처리.ipynb` SQL로 재생성한다.

```mermaid
erDiagram
    analysis_program ||--o{ analysis_program_weekly : "프로그램 ID"
    analysis_program ||--o{ analysis_program_monthly : "프로그램 ID"

    analysis_program {
      bigint program_id PK "분석 프로그램 ID"
      bigint pjseq "댓글 프로그램 ID"
      string program_name "대표 프로그램명"
      string normalized_program_name "비교용 프로그램명"
      string channel_name "대표 채널명"
      string normalized_channel_name "비교용 채널명"
      boolean has_weekly_data "주간 보유"
      boolean has_monthly_data "월간 보유"
      boolean has_comment_data "댓글 매핑"
      string mapping_status "식별 상태"
    }
    analysis_program_weekly {
      bigint program_id PK, FK "프로그램 ID"
      string week_code PK "완료 주차"
      date week_start_date "주 시작일"
      date week_end_date "주 종료일"
      decimal post_count "게시글 수"
      decimal comment_count "댓글 수"
      decimal household_rating "가구 시청률"
      string quality_status "품질 상태"
    }
    analysis_program_monthly {
      bigint program_id PK, FK "프로그램 ID"
      string month_code PK "완료 월"
      date month_start_date "월 시작일"
      date month_end_date "월 종료일"
      decimal post_count "게시글 수"
      decimal tv_household_viewer_count "TV 가구 시청자"
      decimal tv_household_rating "TV 가구 시청률"
      string platform_unit_status "플랫폼 단위 상태"
      string quality_status "품질 상태"
    }
    analysis_keyword_weekly {
      bigint keyword_row_id PK "키워드 행 ID"
      bigint program_id "매핑 프로그램 ID"
      bigint pjseq "댓글 프로그램 ID"
      string week_code "응답 주차"
      string dataset_name "자료 유형"
      string keyword_text "키워드"
      decimal frequency_value "언급 빈도"
      string quality_status "품질 상태"
    }
    analysis_sentiment_weekly {
      bigint sentiment_row_id PK "감성 행 ID"
      bigint program_id "매핑 프로그램 ID"
      bigint pjseq "댓글 프로그램 ID"
      string response_week_code "응답 주차"
      decimal positive_ratio "긍정 비율"
      decimal negative_ratio "부정 비율"
      string quality_status "품질 상태"
    }
    analysis_keyword_edge {
      bigint edge_row_id PK "연관어 행 ID"
      bigint program_id "매핑 프로그램 ID"
      bigint pjseq "댓글 프로그램 ID"
      string week_code "요청 주차"
      string source_keyword "시작 키워드"
      string target_keyword "연결 키워드"
      decimal frequency_value "동시 출현 빈도"
      string quality_status "품질 상태"
    }
```

## raw 원본에서의 유입

| 분석 테이블 | raw 원본 | 생성 방식 |
|---|---|---|
| `analysis_program` | `raw_internet_response`, `raw_total_response` | 프로그램명·채널의 기호·공백만 정리한 조합을 프로그램 1개로 만든다. 다른 채널은 합치지 않는다. |
| `analysis_program_weekly` | `raw_internet_response` | 프로그램·주차별로 내용 지문이 하나일 때만 원본 수치를 숫자형으로 변환한다. 서로 다른 내용이면 충돌 상태와 NULL 수치로 남긴다. |
| `analysis_program_monthly` | `raw_total_response` | 프로그램·월별로 같은 규칙을 적용한다. 주간 값으로 바꾸지 않으며 플랫폼 단위는 미확인 상태를 유지한다. |
| `analysis_keyword_weekly` | `raw_comment_keyword` | 키워드 배열 객체 하나를 한 행으로 보존한다. |
| `analysis_sentiment_weekly` | `raw_comment_sentiment` | 감성 배열 객체 하나를 한 행으로 보존하고 긍정·부정 비율 합계를 검사한다. |
| `analysis_keyword_edge` | `raw_comment_network` | 네트워크 배열 객체 하나를 한 행으로 보존한다. |

댓글 분석 테이블의 `program_id`는 현재 NULL이다. 댓글 원본의 `pjseq=11487`을 프로그램명·채널로 자동 연결할 수 없기 때문이다. 이는 댓글 0건이 아니라 **매핑 근거 미확보** 상태다.
