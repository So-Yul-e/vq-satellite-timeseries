'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getToken } from '@/utils/storage';

export default function Home() {
    const router = useRouter();

    useEffect(() => {
        // 토큰이 있으면 통합 대시보드로, 없으면 로그인으로
        const token = getToken();

        if (token) {
            router.push('/unified-dashboard');
        } else {
            router.push('/login');
        }
    }, [router]);

    return (
        <div className="min-h-screen flex items-center justify-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
    );
}

