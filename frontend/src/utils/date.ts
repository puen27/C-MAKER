// 날짜·시간 표시 유틸. 업무 기준일(명부 날짜)은 항상 한국 시간(Asia/Seoul)으로 계산한다.

const KST_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const KST_DATETIME = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const KST_WEEKDAY = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', weekday: 'short' });

/** YYYY-MM-DD(KST 업무일) → 요일 한 글자, 예: "화" */
export function formatWeekdayKst(date: string): string {
  const parsed = new Date(`${date}T12:00:00+09:00`);
  return Number.isNaN(parsed.getTime()) ? '' : KST_WEEKDAY.format(parsed);
}

/** 오늘 날짜(KST), YYYY-MM-DD */
export function todayKst(): string {
  return KST_DATE.format(new Date());
}

/** ISO 시각 → "MM. DD. HH:mm" (KST) */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  return KST_DATETIME.format(new Date(iso));
}

/** 남은 초 → "MM:SS" */
export function formatCountdown(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}
