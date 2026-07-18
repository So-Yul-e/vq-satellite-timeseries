/**
 * LoadingState — 05_design-common-system.md 계약
 * 로딩 상태의 구현체 자체. animate-spin 기반 스피너로 통일.
 * 무한 로딩 방지: 폴링 기반 로딩(VQ 파이프라인 등)은 호출부가 타임아웃 상태(ErrorBanner)로
 * 전이시킬 책임을 가진다(FR-401).
 */

interface LoadingStateProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

const SIZE_CLASS: Record<NonNullable<LoadingStateProps['size']>, string> = {
  sm: 'h-5 w-5 border-2',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-b-2',
};

export default function LoadingState({ size = 'md', label }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div
        className={`animate-spin rounded-full border-indigo-500 border-t-transparent ${SIZE_CLASS[size]}`}
        role="status"
        aria-label={label ?? '로딩 중'}
      />
      {label && <p className="text-sm text-slate-400 mt-3">{label}</p>}
    </div>
  );
}
