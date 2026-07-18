/**
 * 안전한 Storage 접근 헬퍼 함수
 * Storage 접근이 차단된 환경에서도 오류 없이 동작하도록 처리
 * 모든 Storage 접근을 직접 try-catch로 감싸서 오류를 완전히 방지합니다.
 */

/**
 * localStorage에서 안전하게 값을 가져옵니다
 * @param key 저장된 키
 * @returns 저장된 값 또는 null
 */
export function getLocalStorage(key: string): string | null {
  if (typeof window === 'undefined') return null;
  
  try {
    return localStorage.getItem(key);
  } catch (error: any) {
    // Storage 접근이 완전히 차단된 경우
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      // 오류를 콘솔에 표시하지 않고 조용히 메모리 폴백
      if (key === 'token') {
        return (window as any).__tempToken || null;
      }
      return null;
    }
    // 다른 오류는 경고만 표시
    console.warn('localStorage 접근 실패:', error);
    if (key === 'token') {
      return (window as any).__tempToken || null;
    }
    return null;
  }
}

/**
 * sessionStorage에서 안전하게 값을 가져옵니다
 * @param key 저장된 키
 * @returns 저장된 값 또는 null
 */
export function getSessionStorage(key: string): string | null {
  if (typeof window === 'undefined') return null;
  
  try {
    return sessionStorage.getItem(key);
  } catch (error: any) {
    // Storage 접근이 완전히 차단된 경우
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      if (key === 'token') {
        return (window as any).__tempToken || null;
      }
      return null;
    }
    console.warn('sessionStorage 접근 실패:', error);
    if (key === 'token') {
      return (window as any).__tempToken || null;
    }
    return null;
  }
}

/**
 * localStorage에 안전하게 값을 저장합니다
 * @param key 저장할 키
 * @param value 저장할 값
 * @returns 저장 성공 여부
 */
export function setLocalStorage(key: string, value: string): boolean {
  if (typeof window === 'undefined') return false;
  
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (error: any) {
    // Storage 접근이 완전히 차단된 경우
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      // 메모리 폴백 (조용히 처리, 오류 표시 안 함)
      if (key === 'token') {
        (window as any).__tempToken = value;
      }
      return false;
    }
    // 다른 오류는 경고만 표시
    console.warn('localStorage 저장 실패:', error);
    if (key === 'token') {
      (window as any).__tempToken = value;
    }
    return false;
  }
}

/**
 * sessionStorage에 안전하게 값을 저장합니다
 * @param key 저장할 키
 * @param value 저장할 값
 * @returns 저장 성공 여부
 */
export function setSessionStorage(key: string, value: string): boolean {
  if (typeof window === 'undefined') return false;
  
  try {
    sessionStorage.setItem(key, value);
    return true;
  } catch (error: any) {
    // Storage 접근이 완전히 차단된 경우
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      if (key === 'token') {
        (window as any).__tempToken = value;
      }
      return false;
    }
    console.warn('sessionStorage 저장 실패:', error);
    if (key === 'token') {
      (window as any).__tempToken = value;
    }
    return false;
  }
}

/**
 * localStorage에서 안전하게 값을 제거합니다
 * @param key 제거할 키
 */
export function removeLocalStorage(key: string): void {
  if (typeof window === 'undefined') return;
  
  try {
    localStorage.removeItem(key);
  } catch (error: any) {
    // Storage 접근이 차단된 경우 조용히 처리
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      // 오류 표시 안 함
    } else {
      console.warn('localStorage 제거 실패:', error);
    }
  } finally {
    // 메모리에서도 제거 (항상 실행)
    if (key === 'token') {
      delete (window as any).__tempToken;
    }
  }
}

/**
 * sessionStorage에서 안전하게 값을 제거합니다
 * @param key 제거할 키
 */
export function removeSessionStorage(key: string): void {
  if (typeof window === 'undefined') return;
  
  try {
    sessionStorage.removeItem(key);
  } catch (error: any) {
    // Storage 접근이 차단된 경우 조용히 처리
    if (error.name === 'SecurityError' || error.message?.includes('not allowed')) {
      // 오류 표시 안 함
    } else {
      console.warn('sessionStorage 제거 실패:', error);
    }
  } finally {
    // 메모리에서도 제거 (항상 실행)
    if (key === 'token') {
      delete (window as any).__tempToken;
    }
  }
}

/**
 * 토큰을 안전하게 가져옵니다 (localStorage 우선, 없으면 sessionStorage, 없으면 메모리)
 * 모든 오류를 완전히 처리하여 절대 오류를 throw하지 않습니다.
 */
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  
  try {
    // localStorage에서 먼저 시도
    try {
      const localToken = localStorage.getItem('token');
      if (localToken) return localToken;
    } catch (e: any) {
      // localStorage 접근 실패 시 조용히 무시
      if (e.name === 'SecurityError' || e.message?.includes('not allowed')) {
        // 오류 표시 안 함
      }
    }
    
    // sessionStorage에서 시도
    try {
      const sessionToken = sessionStorage.getItem('token');
      if (sessionToken) return sessionToken;
    } catch (e: any) {
      // sessionStorage 접근 실패 시 조용히 무시
      if (e.name === 'SecurityError' || e.message?.includes('not allowed')) {
        // 오류 표시 안 함
      }
    }
    
    // 메모리 폴백
    return (window as any).__tempToken || null;
  } catch (error) {
    // 예상치 못한 오류도 조용히 처리
    return (window as any).__tempToken || null;
  }
}





