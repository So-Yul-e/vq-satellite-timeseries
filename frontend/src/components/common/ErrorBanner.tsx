/**
 * ErrorBanner — 05_design-common-system.md 계약
 * 02 IA "에러/로딩 상태 전이" 공통 패턴 + FRD 재시도 계약(FR-201/401 등) 구현체.
 * alert() 단발성 호출 금지 — 모든 에러는 이 컴포넌트로 표시한다.
 */

import { useState } from 'react';

interface ErrorBannerProps {
  message: string;
  onRetry: () => void | Promise<void>;
  variant?: 'inline' | 'banner';
}

export default function ErrorBanner({ message, onRetry, variant = 'banner' }: ErrorBannerProps) {
  const [retrying, setRetrying] = useState(false);

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  };

  const containerClass =
    variant === 'inline'
      ? 'flex items-center justify-between text-sm text-red-400 bg-red-900/20 border border-red-500/30 rounded px-3 py-2'
      : 'flex items-center justify-between bg-red-900/30 border border-red-500/40 rounded-lg px-4 py-3 shadow-lg';

  return (
    <div className={containerClass} role="alert">
      <span className="text-red-300 mr-4">{message}</span>
      <button
        type="button"
        onClick={handleRetry}
        disabled={retrying}
        className="flex-shrink-0 px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:bg-red-800 text-white text-xs font-bold rounded transition-colors flex items-center"
      >
        {retrying && (
          <span className="inline-block h-3 w-3 border-2 border-white border-t-transparent rounded-full animate-spin mr-1.5" />
        )}
        {retrying ? '재시도 중...' : '재시도'}
      </button>
    </div>
  );
}
