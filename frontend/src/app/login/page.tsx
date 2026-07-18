'use client';

import React, { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Broadcast } from '@phosphor-icons/react';
import { setLocalStorage, setSessionStorage } from '@/utils/storage';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Determine initial state from URL
  const initialMode = searchParams.get('mode');
  const [isLogin, setIsLogin] = useState(initialMode !== 'register');

  // Sync state when URL changes (optional, but good for back button)
  React.useEffect(() => {
    setIsLogin(searchParams.get('mode') !== 'register');
  }, [searchParams]);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Dummy state for checkbox
  const [autoLogin, setAutoLogin] = useState(true);

  // Registration state
  const [fullName, setFullName] = useState('');

  const toggleMode = () => {
    const newIsLogin = !isLogin;
    setIsLogin(newIsLogin);
    setError('');
    setPassword('');
    setFullName('');

    // Update URL without refreshing
    const newMode = newIsLogin ? 'login' : 'register';
    router.push(`/login?mode=${newMode}`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        // Login Logic
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/auth/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData,
        });

        if (!response.ok) {
          let errorMessage = '이메일 또는 비밀번호가 올바르지 않습니다';
          if (response.status === 429) {
            // slowapi rate limit — 자격증명 오류와 구분해서 안내
            errorMessage = '로그인 시도가 너무 많습니다. 1분 후 다시 시도해주세요.';
          } else {
            try {
              const errorData = await response.json();
              errorMessage = errorData.detail || errorData.message || errorMessage;
            } catch (parseError) {
              if (response.status === 0 || !response.status) {
                errorMessage = '백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.';
              }
            }
          }
          throw new Error(errorMessage);
        }

        const data = await response.json();

        // 안전한 Storage 접근을 통한 토큰 저장 (오류가 발생해도 계속 진행)
        try {
          if (autoLogin) {
            setLocalStorage('token', data.access_token);
          } else {
            setSessionStorage('token', data.access_token);
          }
        } catch (storageError) {
          // Storage 오류는 무시하고 계속 진행 (이미 헬퍼 함수에서 처리됨)
          console.warn('토큰 저장 중 오류 발생 (메모리에 저장됨):', storageError);
        }

        router.push('/unified-dashboard');
      } else {
        // Register Logic
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/auth/register`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });

        if (!response.ok) {
          let errorMessage = '회원가입에 실패했습니다';
          try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorData.message || errorMessage;
          } catch (parseError) {
            // JSON 파싱 실패 시 상태 코드로 메시지 생성
            if (response.status === 500) {
              errorMessage = '서버 오류가 발생했습니다. 백엔드 서버를 확인해주세요.';
            } else if (response.status === 0 || !response.status) {
              errorMessage = '백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.';
            } else {
              errorMessage = `서버 오류 (${response.status})`;
            }
          }
          throw new Error(errorMessage);
        }

        alert('회원가입이 완료되었습니다! 로그인해주세요.');
        toggleMode();
      }
    } catch (err: any) {
      console.error("Login/Register Error:", err);
      // 네트워크 오류인 경우 더 자세한 메시지 표시
      if (err.message === 'Failed to fetch' || err.name === 'TypeError') {
        setError('백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요. (http://localhost:8000)');
      } else {
        setError(err.message || '알 수 없는 오류가 발생했습니다');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-split-container">
      {/* Left Panel: Branding Image */}
      <div className="login-branding-panel">
        <div>
          <div className="branding-icon"><Broadcast size={40} /></div>
          <h1 className="text-h1 font-bold mb-6">VQ Satellite Platform</h1>
          <p className="text-lg opacity-90 leading-loose">
            AI 기반 위성 영상 분석을 통해<br />
            태양광 패널의 설치 현황을 모니터링하세요.
          </p>
        </div>
        <div className="text-xs opacity-50">
          © {new Date().getFullYear()} VQ Satellite Platform. All rights reserved.
        </div>
      </div>

      {/* Right Panel: Form (Gentok Style) */}
      <div className="login-form-panel">
        <div style={{ width: '100%', maxWidth: '380px' }}>

          {/* Header */}
          <div className="login-title-section">
            <p className="welcome-text">{isLogin ? 'Welcome to' : 'Join to'}</p>
            <h1 className="brand-title">
              <span className="brand-highlight">VQ</span>Satellite
            </h1>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Full Name Input (Register Only) */}
            {!isLogin && (
              <div className="input-group">
                <div className="input-icon-left">
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                </div>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="input-underline"
                  placeholder="Full Name"
                  required={!isLogin}
                />
              </div>
            )}

            {/* Email Input */}
            <div className="input-group">
              <div className="input-icon-left">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
              </div>
              <input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-underline"
                placeholder="Email"
                required
              />
            </div>

            {/* Password Input */}
            <div className="input-group">
              <div className="input-icon-left">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
              </div>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-underline"
                placeholder="Password"
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>
                )}
              </button>
            </div>

            {/* Validation Message Area */}
            {error && (
              <div style={{ color: '#ef4444', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
                {error}
              </div>
            )}

            {/* Options Row (Login Mode Only) */}
            {isLogin && (
              <div className="form-options">
                <label className="custom-checkbox">
                  <input
                    type="checkbox"
                    checked={autoLogin}
                    onChange={(e) => setAutoLogin(e.target.checked)}
                    className="hidden"
                  />
                  <div className="checkbox-visual">
                    {autoLogin && <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>}
                  </div>
                  <span>자동로그인</span>
                </label>

                <Link
                  href="/forgot-password"
                  className="hover:text-blue-600 transition-colors"
                >
                  비밀번호 변경
                </Link>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="btn-login-styled"
              style={{ marginTop: isLogin ? '0' : '1.5rem' }}
            >
              {loading ? '처리중...' : (isLogin ? '로그인' : '회원가입')}
            </button>
          </form>

          {/* Footer Area */}
          <div style={{ marginTop: '4rem', textAlign: 'center' }}>
            <p style={{ color: '#64748b', fontSize: '0.875rem' }}>
              {isLogin ? '아직 계정이 없으신가요?' : '이미 계정이 있으신가요?'} {' '}
              <button
                type="button"
                onClick={toggleMode}
                style={{ color: '#2563eb', fontWeight: 600, textDecoration: 'none', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
              >
                {isLogin ? '회원가입' : '로그인'}
              </button>
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" /></div>}>
      <LoginForm />
    </Suspense>
  );
}