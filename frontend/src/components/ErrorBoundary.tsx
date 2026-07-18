'use client';

import { useEffect } from 'react';
import { setupGlobalErrorHandlers } from '@/utils/errorHandler';

/**
 * 전역 오류 핸들러를 설정하는 컴포넌트
 * 앱의 최상위 레벨에서 한 번만 실행됩니다.
 */
export function ErrorBoundarySetup() {
  useEffect(() => {
    setupGlobalErrorHandlers();
  }, []);

  return null;
}





