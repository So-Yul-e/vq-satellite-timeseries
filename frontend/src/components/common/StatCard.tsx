/**
 * StatCard — 05_design-common-system.md 계약
 * Loading(스켈레톤) / Error("—" + 에러 아이콘) / Empty(0건 명시) 상태를 표현.
 */

import { WarningCircle } from '@phosphor-icons/react';

export type StatCardTone = 'default' | 'info' | 'illegal' | 'legal';

interface StatCardProps {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: StatCardTone;
  trend?: string;
  loading?: boolean;
  error?: boolean;
}

const TONE_CLASS: Record<StatCardTone, string> = {
  default: 'text-white',
  info: 'text-blue-400',
  illegal: 'text-red-400',
  legal: 'text-green-400',
};

export default function StatCard({ label, value, unit, tone = 'default', trend, loading, error }: StatCardProps) {
  return (
    <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
      <p className="text-sm text-slate-400 mb-2">{label}</p>

      {loading ? (
        <div className="h-9 w-24 bg-slate-700 rounded animate-pulse" />
      ) : error ? (
        <p className="text-3xl font-bold text-slate-400 flex items-center">
          — <WarningCircle size={18} weight="fill" className="ml-2 text-slate-400" />
        </p>
      ) : (
        <p className={`text-3xl font-bold ${TONE_CLASS[tone]}`}>
          {value === null || value === undefined ? '데이터 없음' : value}
          {unit && <span className="text-lg ml-1">{unit}</span>}
        </p>
      )}

      {trend && !loading && !error && <p className="text-xs text-slate-400 mt-2">{trend}</p>}
    </div>
  );
}
