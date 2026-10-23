# corp-mail-outreach-v2

미수채권(NPL/채권추심) 관련 B2B 메일을 소량·저속(평일 09:00~18:00, 5분당 1건)으로
발송하는 개인용 로컬 프로그램입니다. 요구사항 전체는 [`requirements.md`](./requirements.md)를
참조하세요 (이 프로그램에 대해 작업할 때는 항상 그 문서를 먼저 확인합니다).
(법인보험 관련 내용은 2026-09-09부로 개발 범위에서 제외되었습니다.)

이 레포는 이전 `corp-mail-outreach` 레포를 대체하는 새 버전입니다. 가장 큰 차이는
**타겟리스트 소스에 대해 특정 채널을 가정하지 않는다는 점**입니다 — 사용자가 어떤 경로로든
직접 확보한 엑셀 파일을 그대로 입력받아 처리합니다 (requirements.md 2.2 참조).

## 실행 환경

이 프로그램은 **사용자의 로컬 PC(Windows 노트북)에서만** 동작합니다. 서버 배포나
웹 업로드 화면은 없습니다 (개인정보를 외부 서버에 올리지 않기 위함, requirements.md 2.7 참조).

- 데이터 적재(엑셀 → DB): 로컬 Python 배치 스크립트
- 메일 발송: 작업 스케줄러가 `scripts\send_cycle.py`를 실행해 Gmail SMTP(앱 비밀번호)로 직접 발송 (Claude 호출 없음)

## 처음 설치 시 (로컬 노트북에서)

```powershell
cd C:\Users\jusuk\corp-mail-outreach-v2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\init_db.py
```

`corp_mail_outreach.db` 파일이 레포 루트에 생성됩니다 (개인정보가 담기므로 `.gitignore`에
의해 git에는 절대 올라가지 않습니다).

## 1. 엑셀 데이터 준비

사용자가 직접 확보한 엑셀 파일을 아무 곳에나 둡니다 (예: 이 레포 안의 `download\` 폴더).
특정 URL의 파일을 대신 받아오고 싶다면:

```powershell
python scripts\download_source.py --url "https://...실제파일URL..."
```

(사용자가 지정한 파일 1건만 받아오는 것으로, 자동으로 여러 사이트를 돌며 데이터를 수집하는
크롤러가 아닙니다 — requirements.md 2.2 참조)

## 2. 엑셀 적재하기

```powershell
python scripts\import_excel.py --file "download\실제파일명.xlsx"
```

- 헤더는 `scripts\column_mapping.py`의 별칭 테이블로 자동 정규화됩니다. 필요한 필드는
  사업자등록번호/지역/상호/대표자명/이메일 5개뿐이며, 구매 DB 엑셀에 흔한 재무정보·주주정보 등
  나머지 수십~수백 개 컬럼은 매핑 안 돼도 에러 없이 그냥 무시됩니다.
- **필수 필드**(사업자등록번호, 상호)를 못 찾으면 중단하고 헤더 전체 목록을 보여줍니다.
  이 경우 로컬 Claude Code에게 "이 컬럼들이 뭔지 확인해서 다시 적재해줘"라고 요청하면 됩니다.
  헤더 텍스트로 지정하려면 `--mapping-overrides`, 엑셀 열 문자(A, B, ... AM 등)로
  바로 지정하려면 `--letter-overrides`를 씁니다. **`key=value` 형식이며 JSON이
  아닙니다** — Windows PowerShell/cmd에서 큰따옴표 섞인 JSON을 넘기면 셸마다
  따옴표 처리 방식이 달라 깨지기 쉬워서, 따옴표가 필요 없는 이 형식을 씁니다:
  ```powershell
  python scripts\import_excel.py --file "download\실제파일명.xlsx" --letter-overrides "AM=email"
  ```
  여러 개는 쉼표로 구분합니다: `--letter-overrides "AM=email,C=business_reg_no"`
- **선택 필드**(지역, 대표자명, 이메일)를 못 찾으면 중단하지 않고 안내만 하며 적재는 계속됩니다.
- 일부 엑셀은 1행이 병합된 대분류 제목이고 실제 항목명이 2행에 있습니다. 이 경우
  `--header-row 2`를 추가하세요:
  ```powershell
  python scripts\import_excel.py --file "download\실제파일명.xlsx" --header-row 2
  ```
- 사업자등록번호가 이미 DB에 있으면 해당 행은 자동으로 건너뜁니다(중복 미적재).
- 신규 레코드의 동의 상태는 항상 `unconfirmed`(미확인)로 시작하며, 발송 대상이 되려면
  먼저 아래 3번처럼 `opted_in`으로 바꿔줘야 합니다.

## 3. 발송 전 동의 상태 확인

명시적으로 수신 동의를 받은 대상만 `opted_in`으로 변경합니다. `--note`로 동의를 확인한
경위(예: 전화 통화)를 남겨둡니다:

```powershell
python scripts\set_consent.py --business-reg-no 1234567890 --status opted_in --note "전화 동의 확보"
```

전화 등으로 다수 대상에 대해 한 번에 동의를 확인했다면 `--all`로 일괄 처리할 수 있습니다
(이미 `opted_out`으로 수신거부한 레코드는 보호를 위해 대상에서 자동 제외됩니다):

```powershell
python scripts\set_consent.py --all --status opted_in --note "전화 동의 확보"
```

수신거부 회신을 받았다면:

```powershell
python scripts\set_consent.py --business-reg-no 1234567890 --status opted_out --note "수신거부 회신"
```

동의 상태 데이터(사업자등록번호, 이메일 등)와 마찬가지로 `--note`에 남긴 내용도 개인정보를
포함할 수 있으므로 로컬 DB에만 저장되며 git에는 올라가지 않습니다. 이 근거의 사실 여부와
동의 확보 자체의 적법성은 (requirements.md 2.2와 마찬가지로) 사용자 책임입니다 — 프로그램은
입력된 근거를 검증하지 않고 그대로 기록만 합니다.

## 4. 발송 (작업 스케줄러가 자동 수행)

Windows 작업 스케줄러가 평일 15분 간격으로 `scripts\run_send_cycle.ps1`을 실행하고,
`scripts\send_cycle.py`가 아래 과정을 한 번에 처리합니다 (Claude 호출 없음):

1. 발송 가능 여부·대상 판정 (`pick_next_target.evaluate()`)
   (평일 09:00~18:00, 15분당 1건 페이싱, 동의 상태를 모두 자동 검증)
2. 대상이 있으면, `templates\receivables_template.txt`에 `{{company_name}}` 값을
   채워 메일 작성. 인사말은 "{{company_name}} 대표님, 안녕하세요. 신용사회 지킴이
   고려신용정보 이주석 팀장입니다."로 시작하고, 하단에는 고려신용정보 서명
   (신용관리사(국가공인자격사) 이주석, 010-6527-6825 등)이 포함됩니다.
   Gmail SMTP(`smtp.gmail.com:465`, 앱 비밀번호)로 발송합니다.
3. 발송 결과를 send_log에 기록

수동으로 확인하려면 `python scripts\send_cycle.py --dry-run`(발송·기록 없이 대상과 본문만 출력)을
실행합니다. 필요한 `GMAIL_SMTP_USER`, `GMAIL_SMTP_APP_PASSWORD`는 `.env`에 설정합니다.

## 5. 이메일 미확보 레코드 보강

전화 등으로 이메일을 알아낸 경우, 해당 레코드의 이메일만 예외적으로 갱신합니다:

```powershell
python scripts\update_email.py --business-reg-no 1234567890 --email hong@example.com
```

## 6. 자동 발송이 안정적으로 돌도록 로컬 PC 상태 점검 (Windows)

작업 스케줄러로 자동 실행하는 경우, 발송 시간대(평일 09:00~18:00)에 아래가 유지되어야 합니다.

**절전/최대절전 해제** (AC 전원 연결 시 절대 절전 안 함):
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

**노트북 덮개를 닫아도 절전 안 되게** (절전 타임아웃을 꺼도 덮개를 닫으면 강제 절전되는 경우가 많음):
제어판 → 전원 옵션 → "덮개를 닫을 때의 동작 선택" → 전원에 연결된 상태에서 **"아무 작업 안 함"**으로 변경
(명령어로도 가능: `powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0` 후 `powercfg /setactive SCHEME_CURRENT`)

**작업 스케줄러가 로그인 여부와 무관하게 실행되는지 확인**:
```powershell
schtasks /query /tn "outbound-gmail_SendCycle" /v /fo list
```
"작업 로그온 유형"이 "로그온한 경우에만"이면 로그아웃/잠금 상태에서 안 돌 수 있습니다.
"사용자가 로그온했는지 여부에 관계없이 실행"으로 바꾸려면 `taskschd.msc` GUI에서 해당 작업
속성 → 일반 탭에서 변경(비밀번호 재입력 필요).

**Wi-Fi 어댑터 절전으로 인한 연결 끊김 방지**: 장치 관리자 → 네트워크 어댑터 → Wi-Fi 속성 →
전원 관리 탭 → "전원 절약을 위해 이 장치를 끌 수 있음" 체크 해제

**매일 아침 5분 점검 루틴** (권장):
```powershell
schtasks /query /tn "outbound-gmail_SendCycle" /v /fo list | findstr /i "마지막"
python scripts\check_db_summary.py
```
"마지막 실행 시간/결과"와 발송 성공 건수 누적 여부를 바로 확인할 수 있습니다. BCC 메일함
(`ljusibm@gmail.com`)에서도 실제 발송 메일이 들어오는지 함께 확인하세요.

## 주의 — 발송 전 알아둘 것

**외부 법률 검토를 반드시 먼저 완료해야 한다는 차단 요건은 2026-09-09부로 폐지했습니다**
(자세한 내용은 `requirements.md` 1장 "법률 검토 게이트" 참조). 다만 광고표시·발신자정보·
수신거부 즉시처리·동의상태 관리·평일 09:00~18:00 발송시간대 제한 등 프로그램에 내장된
실질적 컴플라이언스 장치는 그대로 유지됩니다.

**타겟리스트 데이터 출처의 적법성(수집 경위, 동의 여부 등)은 사용자 책임입니다**
(requirements.md 2.2 참조) — 프로그램은 데이터가 어떻게 확보됐는지, `set_consent.py`의
`--note`에 남긴 동의 확보 근거가 사실인지 검증하지 않습니다.
