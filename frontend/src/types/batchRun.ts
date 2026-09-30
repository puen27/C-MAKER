// 배치 실행(BATCH_RUN)·데이터 신선도 타입 (REQ-17, UC-18, RULE-SENSE-04)

export type BatchRunStatus = 'RUNNING' | 'SUCCESS' | 'FAILED';
export type BatchRunType = 'SCHEDULED' | 'MANUAL';

export interface BatchRun {
  id: number;
  runType: BatchRunType;
  status: BatchRunStatus;
  targetDate: string;
  triggeredByName: string | null;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  /** RUNNING일 때 최근 성공 실행 평균 소요시간으로 추정한 완료 예상 시각 */
  expectedCompletionAt: string | null;
  failureReason: string | null;
}

export interface BatchStatus {
  latestRun: BatchRun | null;
  /** VAL-12: 요청 계정 기준 쿨다운 잔여 시간(초). 0이면 즉시 요청 가능 */
  cooldownRemainingSeconds: number;
  cooldownMinutes: number;
}

export interface BatchTriggerResult {
  run: BatchRun;
  /** RULE-SENSE-06: 이미 실행 중이면 새 실행을 만들지 않고 기존 실행을 돌려준다 */
  alreadyRunning: boolean;
}

export type SourceStatus = 'FRESH' | 'FALLBACK' | 'DEGRADED' | 'UNAVAILABLE' | 'SKIPPED';

export interface SourceFreshness {
  sourceName: string;
  displayName: string;
  status: SourceStatus;
  latestAsOfDate: string | null;
  expectedAsOfDate: string;
  delayDays: number;
  isFallback: boolean;
}

export interface DataFreshness {
  referenceDate: string;
  /** 지연 배너 노출 여부 */
  delayed: boolean;
  maxDelayDays: number;
  todaysListReady: boolean;
  latestRunStatus: BatchRunStatus | null;
  message: string | null;
  sources: SourceFreshness[];
}
