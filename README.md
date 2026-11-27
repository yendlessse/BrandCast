# BrandCast

RACOI 데이터 기반으로 뷰티 브랜드의 방송 PPL 후보를 분석하는 프로젝트입니다.

## 개발 기준

- 상세 범위와 핵심 질문 6개: [`../문서/개발 계획서.md`](../문서/개발%20계획서.md)
- 노트북·폴더 구조와 수집 계획: [`문서/노트북_프로젝트_구조_및_개발계획.md`](문서/노트북_프로젝트_구조_및_개발계획.md)
- 파일별 구현 순서와 완료 기준: [`docs/구현_계획서.md`](docs/구현_계획서.md)
- 저장소 작업 규칙: [`AGENTS.md`](AGENTS.md)

기준 DBMS는 MariaDB입니다. 원본 테이블은 그대로 보존하고, 별도의 분석용 테이블에서 전처리합니다. 분석 지표와 후보 순위는 MariaDB SQL로 계산하며 Python은 공개 자료 수집, SQL 실행 연결, SQL 결과 시각화에 사용합니다. 원본 자료 및 실제 비밀 설정은 저장소에 커밋하지 않습니다.

## 최소 실행 환경

- Python 3.11 이상
- MariaDB 10.6 이상
- MariaDB Connector/C

프로젝트 루트에서 가상환경을 만들고 패키지를 설치합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`.env.example`을 `.env`로 복사한 뒤 로컬 MariaDB 접속 정보, RACOI 기준 URL과 분석 기간을 입력합니다. 실제 `.env`와 비밀번호는 Git에 포함하지 않습니다.

```powershell
Copy-Item .env.example .env
```

MariaDB 데이터베이스와 접속 계정은 노트북 실행 전에 준비해야 합니다. 이후 수집 및 분석 노트북은 `.env.example`에 정의된 환경변수 이름을 공통으로 사용하며, 실제 MariaDB 버전은 `SELECT VERSION()` 결과로 기록합니다.

## 프로젝트 구조

```text
프로젝트_소개/  프로젝트 배경과 분석 페르소나
노트북/         수집·적재·Q1~Q6·최종 검토 노트북
수집/           RACOI 공개 자료 수집 모듈과 실행 진입점
데이터/원본/    수정하지 않는 수집 원본(실제 파일은 Git 제외)
문서/           데이터 사전과 수집·분석 한계
그래프/         질문별 그래프 출력 경로
```

