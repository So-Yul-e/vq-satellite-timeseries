/**
 * 전역 오류 핸들러
 * Storage 접근 오류를 조용히 처리하여 사용자 경험을 개선합니다.
 */

/**
 * Storage 관련 오류인지 확인
 */
function isStorageError(error: any): boolean {
  if (!error) return false;
  
  const errorMessage = error.message || error.toString() || '';
  const errorName = error.name || '';
  
  return (
    errorName === 'SecurityError' ||
    errorName === 'QuotaExceededError' ||
    errorMessage.includes('not allowed') ||
    errorMessage.includes('Access to storage') ||
    errorMessage.includes('Failed to read') ||
    errorMessage.includes('Failed to execute')
  );
}

/**
 * 전역 Promise 오류 핸들러 설정
 */
export function setupGlobalErrorHandlers() {
  if (typeof window === 'undefined') return;

  // Unhandled Promise Rejection 핸들러
  window.addEventListener('unhandledrejection', (event) => {
    const error = event.reason;
    
    // Storage 관련 오류는 조용히 처리
    if (isStorageError(error)) {
      event.preventDefault(); // 오류 전파 방지
      console.warn('Storage 접근 오류가 발생했지만 무시됩니다:', error.message);
      return;
    }
    
    // 다른 오류는 그대로 전파 (개발 중에는 표시)
    if (process.env.NODE_ENV === 'development') {
      console.error('Unhandled Promise Rejection:', error);
    }
  });

  // 전역 오류 핸들러
  window.addEventListener('error', (event) => {
    const error = event.error || event;
    
    // Storage 관련 오류는 조용히 처리
    if (isStorageError(error)) {
      event.preventDefault(); // 오류 전파 방지
      console.warn('Storage 접근 오류가 발생했지만 무시됩니다:', error.message);
      return false; // 오류 전파 방지
    }
    
    // 다른 오류는 그대로 전파
    return true;
  });
}





