# -*- coding: utf-8 -*-
"""
발송 로그를 기록하는 스크립트.
requirements.md 2.4절(발송 로그 요구사항) 참조.

실제 발송(또는 발송 시도)을 마친 직후 결과를 send_log 테이블에 남긴다.
정기 발송은 send_cycle.py가 직접 기록하며, 이 스크립트는 수동 발송 등
별도로 로그를 남겨야 할 때 직접 실행한다.

사용법:
    python scripts/log_send.py --business-reg-no <사업자등록번호> \
        --status success|failed|skipped [--template <템플릿파일명>] [--note <비고>]
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "corp_mail_outreach.db")
KST = timezone(timedelta(hours=9))


def parse_args():
    parser = argparse.ArgumentParser(description="발송 로그 기록")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB 파일 경로")
    parser.add_argument("--business-reg-no", required=True, help="발송 대상 사업자등록번호")
    parser.add_argument("--status", required=True, choices=["success", "failed", "skipped"])
    parser.add_argument("--template", default=None, help="사용한 템플릿 파일명")
    parser.add_argument("--note", default=None, help="비고 (실패 사유 등)")
    return parser.parse_args()


def main():
    args = parse_args()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    sent_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        INSERT INTO send_log (business_reg_no, sent_at, status, template_used, note)
        VALUES (?, ?, ?, ?, ?)
        """,
        (args.business_reg_no, sent_at, args.status, args.template, args.note),
    )
    conn.commit()
    conn.close()
    print(f"발송 로그 기록 완료: {args.business_reg_no} / {args.status}")


if __name__ == "__main__":
    main()
