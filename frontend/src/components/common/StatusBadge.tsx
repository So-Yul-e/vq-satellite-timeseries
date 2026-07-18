/**
 * StatusBadge — 05_design-common-system.md 계약
 * 판정 상태(합법/무허가 의심/검토 필요) 및 매칭 품질 공용 배지.
 * 색상만으로 상태를 구분하지 않는다 — 항상 semantic 색상 + 텍스트 라벨을 함께 렌더링(접근성 기준).
 */

export type StatusBadgeStatus = 'legal' | 'illegal' | 'review';

interface StatusBadgeProps {
  status: StatusBadgeStatus;
  label?: string;
}

const STATUS_CONFIG: Record<StatusBadgeStatus, { defaultLabel: string; className: string }> = {
  legal: {
    defaultLabel: '합법',
    className: 'bg-green-900 text-green-400 border border-green-500/30',
  },
  illegal: {
    defaultLabel: '무허가 의심',
    className: 'bg-red-900 text-red-400 border border-red-500/30',
  },
  review: {
    defaultLabel: '검토 필요',
    className: 'bg-yellow-100 text-yellow-800 border border-yellow-500/30',
  },
};

export default function StatusBadge({ status, label }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-bold ${config.className}`}>
      {label ?? config.defaultLabel}
    </span>
  );
}
