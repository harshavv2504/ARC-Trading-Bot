from datetime import datetime, time, date
import pytz

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_MARKET_START = time(9, 0)

# NSE holidays 2025 (add more as needed)
NSE_HOLIDAYS_2025 = {
    date(2025, 1, 26),  # Republic Day
    date(2025, 3, 14),  # Holi
    date(2025, 4, 14),  # Dr. Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),   # Maharashtra Day
    date(2025, 8, 15),  # Independence Day
    date(2025, 10, 2),  # Gandhi Jayanti
    date(2025, 11, 5),  # Diwali Laxmi Puja
    date(2025, 11, 25), # Christmas (shifted)
    date(2025, 12, 25), # Christmas
}

NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 20),  # Holi (approx)
    date(2026, 4, 3),   # Good Friday (approx)
    date(2026, 4, 14),  # Dr. Ambedkar Jayanti
    date(2026, 5, 1),   # Maharashtra Day
    date(2026, 8, 15),  # Independence Day
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 12, 25), # Christmas
}

NSE_HOLIDAYS = NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


def now_ist() -> datetime:
    return datetime.now(IST)


def is_market_open() -> bool:
    now = now_ist()
    if now.weekday() >= 5:
        return False
    if now.date() in NSE_HOLIDAYS:
        return False
    t = now.time().replace(second=0, microsecond=0)
    return MARKET_OPEN <= t <= MARKET_CLOSE


def is_pre_market() -> bool:
    now = now_ist()
    if now.weekday() >= 5 or now.date() in NSE_HOLIDAYS:
        return False
    t = now.time().replace(second=0, microsecond=0)
    return PRE_MARKET_START <= t < MARKET_OPEN


def seconds_until_market_open() -> float:
    now = now_ist()
    target = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if now >= target:
        target = target.replace(day=target.day + 1)
    return (target - now).total_seconds()


def is_trading_day() -> bool:
    now = now_ist()
    return now.weekday() < 5 and now.date() not in NSE_HOLIDAYS
