# -*- coding: utf-8 -*-
"""
발송 사이클을 1회 수행하는 스크립트 (대상선정 + 본문작성 + SMTP발송 + 로그기록).
requirements.md 2.5(발송 방식·페이싱), 2.6(실행 아키텍처) 참조.

기존에는 매 사이클 로컬 Claude Code(`claude -p`)가 Gmail MCP로 발송했으나, Claude 주간 사용
한도 소진 시 발송이 통째로 멈추는 문제(2026-10-22 장애)가 있어 smtplib 직접 발송으로 전환했다.
Claude 호출 없이 이 스크립트 하나가 전 과정을 처리하며, 작업 스케줄러가 run_send_cycle.ps1을
통해 15분 간격으로 실행한다.

발송 가능 여부 판정(동의·이메일·중복·시간대·페이싱)은 pick_next_target.evaluate()를 그대로 쓴다.

필요한 환경변수 (프로젝트 루트의 .env 파일 또는 OS 환경변수):
    GMAIL_SMTP_USER           발송 Gmail 주소
    GMAIL_SMTP_APP_PASSWORD   Google 앱 비밀번호 (16자리, 2단계 인증 필요)

사용법:
    python scripts/send_cycle.py [--db <DB경로>] [--dry-run]

--dry-run: 실제 SMTP 발송과 로그 기록 없이 대상 선정과 본문 구성 결과만 출력한다.

종료 코드: 0 = 발송 성공 또는 정상 보류(발송 불가), 1 = 설정 오류 또는 발송 실패
"""
import argparse
import os
import smtplib
import sqlite3
import sys
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from log_send import KST  # noqa: E402
from pick_next_target import DEFAULT_DB_PATH, evaluate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "templates" / "receivables_template.txt"
BCC_ADDRESS = "ljusibm@gmail.com"  # requirements.md: 실제 발송 시 항상 BCC 포함
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def parse_args():
    parser = argparse.ArgumentParser(description="발송 사이클 1회 수행 (SMTP 직접 발송)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB 파일 경로")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE_PATH), help="메일 템플릿 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="실제 발송 없이 대상 선정·본문 구성만 확인")
    return parser.parse_args()


def load_env(path):
    """.env의 KEY=VALUE 줄을 환경변수로 읽는다 (이미 설정된 OS 환경변수가 우선)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_template(path):
    """템플릿 파일의 1행을 제목("제목: ...")으로, 나머지를 본문으로 분리한다."""
    text = Path(path).read_text(encoding="utf-8")
    first_line, _, rest = text.partition("\n")
    if not first_line.startswith("제목:"):
        raise ValueError(f"템플릿 1행은 '제목:'으로 시작해야 합니다: {path}")
    return first_line[len("제목:"):].strip(), rest.lstrip("\r\n")


def render(text, company_name):
    return text.replace("{{company_name}}", company_name)


def send_mail(user, password, to_email, subject, body):
    """smtplib으로 Gmail SMTP를 통해 발송한다. BCC는 헤더에 넣지 않고 봉투 수신자에만 포함한다."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60) as server:
        server.login(user, password)
        server.sendmail(user, [to_email, BCC_ADDRESS], msg.as_string())


def write_log(db_path, business_reg_no, status, template_name, note=None):
    sent_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO send_log (business_reg_no, sent_at, status, template_used, note) VALUES (?, ?, ?, ?, ?)",
            (business_reg_no, sent_at, status, template_name, note),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    args = parse_args()
    load_env(REPO_ROOT / ".env")

    result = evaluate(args.db)
    if not result["eligible"]:
        print(f"발송 보류: {result['reason']}")
        return 0
    target = result["target"]

    subject_tpl, body_tpl = load_template(args.template)
    subject = render(subject_tpl, target["company_name"])
    body = render(body_tpl, target["company_name"])
    template_name = Path(args.template).name

    if args.dry_run:
        print("[DRY RUN] 실제 발송하지 않습니다.")
        print(f"대상: {target['business_reg_no']} / {target['company_name']} / {target['email']}")
        print(f"제목: {subject}")
        print("---- 본문 ----")
        print(body)
        return 0

    user = os.environ.get("GMAIL_SMTP_USER", "")
    password = os.environ.get("GMAIL_SMTP_APP_PASSWORD", "").replace(" ", "")
    if not user or not password:
        # 설정 오류는 대상 문제가 아니므로 send_log(failed)에 남기지 않는다.
        print("설정 오류: GMAIL_SMTP_USER / GMAIL_SMTP_APP_PASSWORD가 .env에 없습니다.")
        return 1

    try:
        send_mail(user, password, target["email"], subject, body)
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 그대로 로그에 남기기 위함
        write_log(args.db, target["business_reg_no"], "failed", template_name, note=str(exc)[:500])
        print(f"발송 실패: {target['business_reg_no']} / {type(exc).__name__}: {exc}")
        return 1

    try:
        write_log(args.db, target["business_reg_no"], "success", template_name)
    except Exception as exc:  # noqa: BLE001
        # 메일은 이미 나갔는데 로그가 안 남으면 같은 대상에게 중복 발송될 수 있으므로 크게 알린다.
        print(f"[긴급] 발송은 성공했으나 로그 기록 실패 - 수동으로 success 기록 필요: "
              f"{target['business_reg_no']} / {exc}")
        return 1

    print(f"발송 성공: {target['business_reg_no']} / {target['company_name']} / {target['email']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
