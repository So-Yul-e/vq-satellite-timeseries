'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { LockKey } from '@phosphor-icons/react';

function ResetPasswordForm() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        if (!token) {
            setError('유효하지 않은 접근입니다. 이메일 링크를 통해 접속해주세요.');
        }
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (password !== confirmPassword) {
            setError('비밀번호가 일치하지 않습니다.');
            return;
        }

        if (password.length < 8) {
            setError('비밀번호는 최소 8자 이상이어야 합니다.');
            return;
        }

        if (!token) {
            setError('토큰이 없습니다.');
            return;
        }

        setIsLoading(true);
        setMessage('');
        setError('');

        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password: password }),
            });

            const data = await response.json();

            if (response.ok) {
                setMessage('비밀번호가 성공적으로 변경되었습니다. 잠시 후 로그인 페이지로 이동합니다.');
                setTimeout(() => {
                    router.push('/login');
                }, 3000);
            } else {
                setError(data.detail || '비밀번호 변경에 실패했습니다.');
            }
        } catch (err) {
            setError('서버와 통신할 수 없습니다.');
        } finally {
            setIsLoading(false);
        }
    };

    if (!token) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-center p-8 bg-white rounded-xl shadow-lg">
                    <h2 className="text-xl font-bold text-rose-600 mb-4">잘못된 접근</h2>
                    <p className="text-gray-600 mb-6">{error || '토큰이 유효하지 않습니다.'}</p>
                    <Link href="/login" className="text-blue-600 hover:underline font-medium">로그인으로 돌아가기</Link>
                </div>
            </div>
        );
    }

    return (
        <div className="login-split-container">
            {/* Left Panel: Branding Image */}
            <div className="login-branding-panel">
                <div>
                    <div className="branding-icon"><LockKey size={40} /></div>
                    <h1 className="text-h1 font-bold mb-6">Create New Password</h1>
                    <p className="text-lg opacity-90 leading-loose">
                        새로운 비밀번호를 설정하여 계정을 보호하세요.<br />
                        영문, 숫자, 특수문자를 포함하면 더 안전합니다.
                    </p>
                </div>
                <div className="text-xs opacity-50">
                    © {new Date().getFullYear()} VQ Satellite Platform. All rights reserved.
                </div>
            </div>

            {/* Right Panel: Form */}
            <div className="login-form-panel">
                <div style={{ width: '100%', maxWidth: '380px' }}>

                    <div className="login-title-section">
                        <h2 className="text-2xl font-bold text-slate-800 mb-2">새 비밀번호 설정</h2>
                        <p className="text-sm text-slate-400">
                            새로운 비밀번호를 입력해주세요.
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="input-group">
                            <div className="input-icon-left">
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                            </div>
                            <input
                                type="password"
                                required
                                className="input-underline"
                                placeholder="New Password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                            />
                        </div>

                        <div className="input-group">
                            <div className="input-icon-left">
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                            </div>
                            <input
                                type="password"
                                required
                                className="input-underline"
                                placeholder="Confirm Password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                            />
                        </div>

                        {message && (
                            <div className="rounded-md bg-emerald-50 p-4 border border-emerald-100">
                                <p className="text-sm font-medium text-emerald-800">{message}</p>
                            </div>
                        )}

                        {error && (
                            <div className="rounded-md bg-rose-50 p-4 border border-rose-100">
                                <p className="text-sm font-medium text-rose-800">{error}</p>
                            </div>
                        )}

                        <div>
                            <button
                                type="submit"
                                disabled={isLoading || !!message}
                                className="btn-login-styled group relative w-full flex justify-center"
                            >
                                {isLoading ? '변경 중...' : '비밀번호 변경하기'}
                            </button>
                        </div>
                    </form>

                </div>
            </div>
        </div>
    );
}

export default function ResetPasswordPage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 sm:px-6 lg:px-8">
            <Suspense fallback={<div>Loading...</div>}>
                <ResetPasswordForm />
            </Suspense>
        </div>
    );
}
