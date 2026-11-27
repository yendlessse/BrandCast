# RACOI 응답 구조 조사 결과

조사일: 2026년 11월 28일(KST)  
대상 이슈: #3 RACOI 데이터 수집 모듈 구현  
조사 범위: 상세 개발계획 4. 실제 요청 구조 조사, 5. 소량 시범 요청, 6. Excel 응답 구조 확인

## 1. 조사 목적

RACOI 공개 화면과 다운로드 기능에서 실제 응답을 소량 받아 다음 사항을 확인했다.

- 인터넷반응과 종합반응 Excel 다운로드 요청 구조
- 최신 완료 주차와 월 코드
- Excel 시트, 헤더, 병합 셀, 실제 데이터 행과 컬럼 구조
- `pjseq=11487` 댓글반응 상세의 공개 JSON 엔드포인트
- 댓글 키워드, 감성, 워드클라우드와 연관어 데이터 제공 범위
- Q4 관심 주제와 Q6 감성 위험 분석의 구현 가능 범위

이번 조사에서 받은 실제 원본은 `데이터/원본` 아래에 보존하며 `.gitignore`에 따라 Git에는 포함하지 않는다.

## 2. 공식 공개 범위

KOBACO의 RACOI 안내에 따르면 인터넷반응은 주간, 종합반응은 월간 자료이며 2017년 5월 이후 조사를 제공한다. 주요 조사 지표는 미디어버즈의 뉴스·동영상 수와 시청자버즈의 게시글·댓글·동영상 조회 수다.

확인한 공식 페이지:

- KOBACO RACOI 안내: <https://kobaco.co.kr/site/main/content/racoi_info>
- 인터넷반응·종합반응 다운로드: <https://www.racoi.or.kr/kobaco/excel/response.do?menu=ibuzz>
- 댓글반응 상세: <https://www.racoi.or.kr/kobaco/nreport/pjinfo.do?pjseq=11487>

## 3. 다운로드 요청 구조

### 3.1 인터넷반응·종합반응

인터넷반응과 종합반응은 같은 다운로드 화면과 POST 엔드포인트를 사용한다.

| 항목 | 확인 결과 |
|---|---|
| 화면 | `GET /kobaco/excel/response.do?menu=ibuzz` 또는 `menu=total` |
| 다운로드 | `POST /kobaco/excel/mexceldown.do` |
| 인터넷반응 구분 | `rtype=1` |
| 종합반응 구분 | `rtype=2` |
| 기간 코드 | 인터넷반응 `YYYYWW`, 종합반응 `YYYYMM` |
| 응답 | XLSX 첨부 파일 |
| MIME | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

다운로드 폼에서 확인한 주요 필드:

```text
rtype
st
ed
datep_st
datep_ed
filterConditions
parClassList
classList
channelList
siteList
ccSiteList
siteSelectName
category
rcOnlySiteList
```

장르 전체 조건은 `cat001`부터 `cat004`까지의 조건을 JSON 배열로 전달한다. 채널과 세부 사이트를 선택하지 않은 전체 다운로드에서는 관련 목록을 빈 배열로 전달할 수 있었다.

### 3.2 댓글반응 상세

댓글반응 화면은 `application/x-www-form-urlencoded` POST 본문의 `param` 필드에 JSON 객체를 넣어 공개 API를 호출한다.

```text
param={"pjseq":11487,"nweek":"202646"}
```

API 응답 본문은 유효한 JSON이지만 일부 응답에서 `Content-Type` 헤더가 확인되지 않았다. 수집 코드는 헤더만 믿지 않고 JSON 파싱 가능 여부를 함께 검증해야 한다.

## 4. 기준 기간 확인

`/kobaco/select/report.getLastWeekNMonth.do` 응답에서 조사 시점의 최신 완료 기간을 확인했다.

| 구분 | 코드 | 표시명 | 시작일 | 종료일 |
|---|---|---|---|---|
| 인터넷반응 최신 완료 주차 | `202647` | 2026년 11월 3주 | 2026-11-16 | 2026-11-22 |
| 종합반응 최신 완료 월 | `202610` | 2026년 10월 | 2026-10-01 | 2026-10-31 |

`pjseq=11487`의 최신 댓글 날짜는 2026년 11월 9일이며, 댓글반응의 최신 제공 주차는 다음과 같다.

| 프로그램 ID | 최신 댓글 날짜 | 주차 코드 | 표시명 | 기간 |
|---:|---|---|---|---|
| 11487 | 2026-11-09 | `202646` | 2026년 11월 2주 | 2026-11-09 ~ 2026-11-15 |

댓글반응의 최신 주차가 인터넷반응 최신 완료 주차보다 한 주 이전일 수 있으므로 원천별 최신 완료 기준을 따로 기록해야 한다.

## 5. 인터넷반응 Excel 구조

### 5.1 원본 파일

| 항목 | 확인 결과 |
|---|---|
| 파일명 | `인터넷반응DB_2026년11월3주_2026년11월3주.xlsx` |
| 파일 크기 | 29,436 bytes |
| SHA-256 | `FA815BBB2A1AA1C4D924F5D04B998DC5F9CD90B5B54D5D91946EB329FE6FBC90` |
| 시트 | `인터넷반응DB` 1개 |
| XLSX 내부 행 노드 | 158개 |
| 실제 데이터 행 | 154개, Excel 행 8~161 |
| 실제 컬럼 | 18개, A~R |
| 헤더 | Excel 행 6~7의 2단 헤더 |
| 병합 범위 | 10개 |

### 5.2 병합 헤더

```text
A6:A7, B6:B7, C6:C7, D6:D7
E6:G6, H6:I6
J6:L6, M6:N6
O6:P6, Q6:R6
```

### 5.3 의미상 컬럼 구조

| 열 | 상위 분류 | 하위 분류 |
|---|---|---|
| A | 기간 | 주차 코드 |
| B | 프로그램 | 프로그램명 |
| C | 프로그램 | 채널 |
| D | 프로그램 | 요일 |
| E~G | 시청자버즈 건수 | 게시글·댓글·동영상조회 |
| H~I | 미디어버즈 건수 | 뉴스·동영상 |
| J~L | 시청자버즈 점유율 | 게시글·댓글·동영상조회 |
| M~N | 미디어버즈 점유율 | 뉴스·동영상 |
| O~P | 시청자 수 | 가구·2049 |
| Q~R | 시청률 | 가구·2049 |

### 5.4 구조상 주의점

- 워크시트 XML의 `dimension` 값이 실제 범위와 달리 `A1`로 기록되어 있다.
- 행 수나 사용 범위를 `dimension`만으로 판단하면 데이터가 없는 것으로 오인할 수 있다.
- 실제 행 노드와 헤더 행을 직접 읽어 데이터 범위를 판별해야 한다.
- 시청자 수와 시청률의 `0`이 실제 0인지 미수집 기본값인지는 원천 정의와 다른 기간 비교로 추가 확인해야 한다.

## 6. 종합반응 Excel 구조

### 6.1 원본 파일

| 항목 | 확인 결과 |
|---|---|
| 파일명 | `종합반응DB_2026년10월_2026년10월.xlsx` |
| 파일 크기 | 44,341 bytes |
| SHA-256 | `E9B63C919497312377D5F3AE19AED56251D84BF9E5F13E9980869090AE4D4381` |
| 시트 | `종합반응DB` 1개 |
| XLSX 내부 행 노드 | 192개 |
| 실제 데이터 행 | 187개, Excel 행 9~195 |
| 실제 컬럼 | 32개, A~AF |
| 헤더 | Excel 행 6~8의 3단 헤더 |
| 병합 범위 | 17개 |

### 6.2 병합 헤더

```text
A6:A8, B6:B8, C6:C8, D6:D8
E6:I6, J6:AB6, AC6:AD6, AE6:AF6
E7:G7, H7:I7
J7:R7, S7:AA7
AB7:AB8, AC7:AC8, AD7:AD8, AE7:AE8, AF7:AF8
```

### 6.3 의미상 컬럼 구조

| 열 | 상위 분류 | 하위 분류 |
|---|---|---|
| A | 기간 | 월 코드 |
| B | 프로그램 | 프로그램명 |
| C | 프로그램 | 채널 |
| D | 프로그램 | 요일 |
| E~G | 인터넷반응·시청자버즈 | 게시글·댓글·동영상조회 |
| H~I | 인터넷반응·미디어버즈 | 뉴스·동영상 |
| J~R | TV 시청자 수 | 가구·개인·남성·여성·10대·20대·30대·40대·50대 |
| S~AA | TV 시청률 | 가구·개인·남성·여성·10대·20대·30대·40대·50대 |
| AB | TV | VOD |
| AC~AD | PC | 실시간·VOD |
| AE~AF | Mobile | 실시간·VOD |

### 6.4 구조상 주의점

- 인터넷반응과 마찬가지로 워크시트 XML의 `dimension` 값이 `A1`로 기록되어 있다.
- 3단 병합 헤더를 단순히 마지막 헤더 행만 읽으면 상위 의미를 잃는다.
- MariaDB 원본 테이블 컬럼을 확정할 때 6~8행을 결합한 의미상 헤더를 사용해야 한다.
- 동영상조회 헤더에 표시된 `K` 단위와 AB~AF 플랫폼 지표의 정의는 이용가이드 또는 추가 기간 비교로 확인해야 한다.
- 0이 반복되는 VOD·PC·Mobile 지표가 실제 0인지 미제공 값인지 추가 품질검사가 필요하다.

## 7. 댓글반응 JSON 구조

### 7.1 공개 엔드포인트와 응답

| 데이터 | 공개 POST 엔드포인트 | 레코드 수 | 주요 필드 |
|---|---|---:|---|
| 최신 댓글 날짜 | `report.getLatestCommentDate.do` | 1 | `commentyear`, `commentmonth`, `commentday` |
| 날짜의 주차 정보 | `report.getWeekInfoByDate.do` | 1 | `dfm`, `dfm_nm`, `st`, `ed` |
| 댓글 키워드 TOP 20 | `ott.getCommentsTable.do` | 20 | `nweek`, `rk1`, `keyword`, `frequency` |
| 긍정댓글 키워드 TOP 20 | `ott.getPositiveCommentsTable.do` | 20 | `nweek`, `rk1`, `keyword`, `frequency` |
| 긍정·부정 감성 추이 | `ott.getTrendLineChart.do` | 14 | `nweek`, `positivescore`, `negativescore` |
| 긍정·부정 감성 분포 | `ott.getTrendDoughnutChart.do` | 1 | `nweek`, `positivescore`, `negativescore` |
| 감성 워드클라우드 | `ott.getWordCloudChart.do` | 200 | `sentimenttypecode`, `nweek`, `keyword`, `programid`, `frequency` |
| 연관어 중심 키워드 | `ott.getNetworkChart.do` | 7 | `rk1`, `bigram`, `frequency` |
| 연관어 조합 표 | `ott.getNetworkTable.do` | 10 | `rk1`, `bigram`, `frequency` |
| 연관어 네트워크 원천 | `ott.getNetworkSource.do` | 42 | `rk1`, `bigram`, `target`, `frequency` |

### 7.2 감성 코드

공개 화면 JavaScript의 워드클라우드 렌더링 순서로 다음 매핑을 확인했다.

| `sentimenttypecode` | 의미 | 조사 주차 레코드 수 |
|---:|---|---:|
| 1 | 긍정 | 25 |
| 2 | 부정 | 22 |
| 3 | 중립 | 153 |

### 7.3 감성 데이터 제약

- 감성 추이와 도넛 분포 API는 `positivescore`와 `negativescore` 두 값만 제공한다.
- 두 값은 조사 표본에서 합계가 1인 비율 형태다.
- 중립 워드클라우드 키워드는 제공되지만 중립 감성 비율이나 건수는 제공되지 않는다.
- 현재 Q6 계획의 긍정·중립·부정 100% 누적 막대그래프는 이 API만으로 직접 구현할 수 없다.
- 추가 공식 원천에서 중립 비율을 찾지 못하면 Q6 그래프를 긍정·부정 2분포로 수정하거나 중립을 미제공으로 표시해야 한다.

### 7.4 분석 가능성 판단

| 질문 | 판단 | 근거 |
|---|---|---|
| Q4 관심 주제 | 구현 가능 | 일반·긍정 키워드 빈도, 감성 워드클라우드, 연관어 조합과 네트워크 제공 |
| Q5 최근 관심 추이 | 댓글 감성 보조지표 가능 | 14주 긍정·부정 추이 제공 |
| Q6 감성 위험 | 부분 구현 가능 | 긍정·부정 비율과 추이 제공, 중립 비율·감성 원문·감성 건수 미제공 |

댓글 원문은 응답에 포함되지 않았고 집계 키워드와 점수만 제공됐다. 프로젝트는 공개 집계 결과를 우선 사용하며 댓글 원문을 별도로 수집하거나 자체 감성 모델로 대체하지 않는다.

## 8. 원본 보존 결과

실제 소량 원본은 다음 위치에 저장했다.

```text
데이터/원본/인터넷반응_주간/
└── 인터넷반응DB_2026년11월3주_2026년11월3주.xlsx

데이터/원본/종합반응_월간/
└── 종합반응DB_2026년10월_2026년10월.xlsx

데이터/원본/댓글반응_상세/
├── 댓글반응_상세_pjseq-11487_202646_comments_table.json
├── 댓글반응_상세_pjseq-11487_202646_positive_comments_table.json
├── 댓글반응_상세_pjseq-11487_202646_sentiment_trend.json
├── 댓글반응_상세_pjseq-11487_202646_sentiment_distribution.json
├── 댓글반응_상세_pjseq-11487_202646_word_cloud.json
├── 댓글반응_상세_pjseq-11487_202646_keyword_network.json
├── 댓글반응_상세_pjseq-11487_202646_keyword_network_table.json
└── 댓글반응_상세_pjseq-11487_202646_keyword_network_source.json
```

최신 댓글 날짜와 주차 정보 JSON도 같은 폴더에 보존했다. 모든 실제 원본은 Git 제외 대상이다.

## 9. 수집 모듈 구현에 반영할 결정

1. 인터넷반응과 종합반응은 공식 `mexceldown.do` POST 다운로드를 사용한다.
2. Excel은 응답 바이트를 수정하지 않고 XLSX로 보존한다.
3. 파일 형식은 MIME과 ZIP 시그니처를 함께 검사한다.
4. 실제 데이터 범위는 XLSX `dimension`에 의존하지 않고 행 노드와 헤더 위치로 판단한다.
5. 인터넷반응은 2단 헤더, 종합반응은 3단 헤더 구조를 메타데이터에 기록한다.
6. 댓글반응은 공개 JSON POST API를 원천별로 저장한다.
7. JSON 응답은 `Content-Type` 헤더가 없을 수 있으므로 본문 파싱 검증을 수행한다.
8. 댓글반응 최신 주차는 인터넷반응 최신 주차와 별도로 조회한다.
9. 원본 파일은 파일 시스템에 보존하고 이슈 #5에서 행 단위 MariaDB raw 테이블로 적재한다.
10. Q6의 중립 감성 비율은 미제공 상태로 기록하고 그래프 명세 변경 여부를 후속 검토한다.

## 10. 남은 확인 사항

- 인터넷반응·종합반응의 1년 기간을 한 요청으로 내려받을 때의 파일 크기와 서버 제한
- 장르·채널·사이트별 필터 조합의 실제 요청 결과
- Excel의 시청자 수·시청률 0이 실제 0인지 미제공 기본값인지
- 종합반응 동영상조회 `K` 단위의 정확한 정의
- TV VOD·PC·Mobile 지표의 단위와 0 의미
- 다른 프로그램에서도 댓글반응 JSON 스키마가 동일한지
- 댓글반응 API의 요청 빈도 제한과 안정적인 재시도 간격
