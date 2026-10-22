# -*- coding: utf-8 -*-
"""
다음 발송 대상 1건을 선정하는 스크립트.
requirements.md 2.1(컴플라이언스), 2.5(발송 방식·페이싱), 2.6(실행 아키텍처) 참조.

로컬 Claude Code가 (Routine 등으로) 15분 간격 근처에 이 스크립트를 실행해
발송 가능 여부와 대상을 확인한다. 이 스크립트는 조회만 수행하며,
실제 Gmail 발송은 로컬 Claude Code가 Gmail MCP 커넥터로 직접 수행한다.
발송 후에는 log_send.py로 결과를 기록해야 한다.

발송 자격 조건 (모두 만족해야 함):
    - consent_status = 'opted_in'  (명시적 수신 동의)
    - email_status = 'present'     (이메일 보유)
    - 과거에 status='success'로 발송된 적 없는 대상 (동일 대상 중복 발송 금지)
    - 현재 시각이 평일(월~금) 09:00~18:00 (KST)이고 대한민국 법정공휴일이 아님
    - 가장 최근 성공 발송으로부터 15분 이상 경과 (15분당 1건 페이싱)

사용법:
    python scripts/pick_next_target.py [--db <DB경로>]

출력: JSON 1줄
    - 발송 가능: {"eligible": true, "target": {...}}
    - 발송 불가: {"eligible": false, "reason": "..."}
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "corp_mail_outreach.db")
KST = ZoneInfo("Asia/Seoul")
BUSINESS_START_HOUR = 9  # 09:00 이상
BUSINESS_END_HOUR = 18   # 18:00 미만
WEEKDAYS_ONLY = True     # 월(0)~금(4)만 발송, 토·일 제외
MIN_INTERVAL_SECONDS = 900  # 15분당 1건

# 2026~2027년 대한민국 법정공휴일 (관공서의 공휴일에 관한 규정, 대체공휴일 포함).
# 외부 API 대신 하드코딩: 이 스크립트는 스케줄러가 무인으로 실행하므로 네트워크
# 의존성을 늘리지 않기 위함. 연도가 바뀌면 다음 해 목록으로 갱신 필요.
KOREAN_HOLIDAYS = {
    "2026-01-01",  # 신정
    "2026-02-16", "2026-02-17", "2026-02-18",  # 설날 연휴
    "2026-03-01", "2026-03-02",  # 삼일절 (3/2 대체공휴일)
    "2026-05-05",  # 어린이날
    "2026-05-24", "2026-05-25",  # 부처님오신날 (5/25 대체공휴일)
    "2026-06-06",  # 현충일
    "2026-08-15", "2026-08-17",  # 광복절 (8/17 대체공휴일)
    "2026-09-24", "2026-09-25", "2026-09-26",  # 추석 연휴
    "2026-10-03", "2026-10-05",  # 개천절 (10/5 대체공휴일)
    "2026-10-09",  # 한글날
    "2026-12-25",  # 크리스마스
    # 2027년 (대체공휴일 포함). 현충일(6/6, 일요일)은 대체공휴일 적용 대상이 아님.
    "2027-01-01",  # 신정
    "2027-02-05", "2027-02-06", "2027-02-07", "2027-02-08",  # 설날 연휴 (2/8 대체공휴일)
    "2027-03-01",  # 삼일절
    "2027-05-05",  # 어린이날
    "2027-05-13",  # 부처님오신날
    "2027-08-15", "2027-08-16",  # 광복절 (8/16 대체공휴일)
    "2027-09-14", "2027-09-15", "2027-09-16",  # 추석 연휴
    "2027-10-03", "2027-10-04",  # 개천절 (10/4 대체공휴일)
    "2027-10-09", "2027-10-11",  # 한글날 (10/11 대체공휴일)
    "2027-12-25", "2027-12-27",  # 크리스마스 (12/27 대체공휴일)
}


def parse_args():
    parser = argparse.ArgumentParser(description="다음 발송 대상 1건 선정")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB 파일 경로")
    return parser.parse_args()


def emit(payload):
    # ensure_ascii=True(기본값)로 한글을 \uXXXX로 이스케이프해서 출력한다.
    # Windows 콘솔 코드페이지가 한글을 못 받아 일부 바이트가 손실되는 문제를
    # (예: 상호명이 깨져서 표시됨) 피하기 위함 - JSON을 파싱하는 쪽에서는
    # \uXXXX가 원래 한글로 정확히 복원된다.
    print(json.dumps(payload, ensure_ascii=True))


def evaluate(db_path):
    """현재 시점의 발송 가능 여부를 판정한다. emit()에 넘기는 dict와 같은 형식을 반환한다.
    send_cycle.py(SMTP 직접 발송)도 이 함수를 그대로 써서 판정 기준을 한 곳에서만 관리한다."""
    now = datetime.now(KST)

    if WEEKDAYS_ONLY and now.weekday() >= 5:  # 5=토, 6=일
        return {"eligible": False, "reason": "주말에는 발송할 수 없습니다 (평일 09:00~18:00 KST만 발송)."}

    today_str = now.strftime("%Y-%m-%d")
    if today_str in KOREAN_HOLIDAYS:
        return {"eligible": False, "reason": f"법정공휴일({today_str})에는 발송할 수 없습니다."}

    if not (BUSINESS_START_HOUR <= now.hour < BUSINESS_END_HOUR):
        return {"eligible": False, "reason": "업무시간(평일 09:00~18:00 KST) 외에는 발송할 수 없습니다."}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        # 페이싱 확인: 마지막 성공 발송으로부터 15분이 지나야 함
        # 주의: sent_at은 KST(Asia/Seoul) 기준으로 저장된다 (log_send.py 참조).
        cur.execute(
            "SELECT sent_at FROM send_log WHERE status = 'success' ORDER BY sent_at DESC LIMIT 1"
        )
        last = cur.fetchone()
        if last:
            last_sent_kst = datetime.fromisoformat(last["sent_at"]).replace(tzinfo=KST)
            elapsed = (datetime.now(KST) - last_sent_kst).total_seconds()
            if elapsed < MIN_INTERVAL_SECONDS:
                wait_sec = int(MIN_INTERVAL_SECONDS - elapsed)
                return {
                    "eligible": False,
                    "reason": f"마지막 발송 후 15분이 지나지 않았습니다. 약 {wait_sec}초 후 다시 확인하세요.",
                }

        # 발송 대상 조회: 동의완료 + 이메일보유 + 미발송
        cur.execute(
            """
            SELECT business_reg_no, company_name, representative_name, email
            FROM companies
            WHERE consent_status = 'opted_in'
              AND email_status = 'present'
              AND business_reg_no NOT IN (
                  SELECT business_reg_no FROM send_log WHERE status = 'success'
              )
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        target = cur.fetchone()
    finally:
        conn.close()

    if not target:
        return {"eligible": False, "reason": "발송 가능한(동의완료·이메일보유·미발송) 대상이 없습니다."}

    return {
        "eligible": True,
        "target": {
            "business_reg_no": target["business_reg_no"],
            "company_name": target["company_name"],
            "representative_name": target["representative_name"],
            "email": target["email"],
        },
    }


def main():
    args = parse_args()
    emit(evaluate(args.db))


if __name__ == "__main__":
    main()
