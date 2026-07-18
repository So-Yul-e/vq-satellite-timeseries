'use client';

/**
 * 통합 대시보드 — 02 IA 18~41행, 04 FRD FR-101/FR-501
 * dashboard/vq-dashboard/detect 3개 화면의 실기능을 이관한 유일한 대시보드.
 * mock 데이터 렌더링 금지 — 서버 응답만 렌더링(FR-501).
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ClockCounterClockwise, MapTrifold, ShieldWarning, FileText, ChartBar, SignOut } from '@phosphor-icons/react';
import { getToken, removeLocalStorage, removeSessionStorage } from '@/utils/storage';
import { apiClient, isApiSuccess } from '@/utils/apiClient';
import type { MatchingStats, SolarPermitStats } from '@/types/api';
import TabNav, { TabNavItem } from '@/components/common/TabNav';
import LoadingState from '@/components/common/LoadingState';
import TimeSeriesTab from '@/components/dashboard/tabs/TimeSeriesTab';
import AiDetectionTab from '@/components/dashboard/tabs/AiDetectionTab';
import IllegalDbTab from '@/components/dashboard/tabs/IllegalDbTab';
import PermitsTab from '@/components/dashboard/tabs/PermitsTab';
import StatsTab from '@/components/dashboard/tabs/StatsTab';

// 2026-07-17 기능별 탭 분리 재편(02 IA 21행): "동일 여정이 아니면 탭을 분리한다".
// 시계열 변화탐지(프로젝트 본래 목적)를 첫 탭으로 승격.
const TABS: TabNavItem[] = [
  { id: 'timeseries', name: '시계열 변화탐지', icon: <ClockCounterClockwise size={18} /> },
  { id: 'detect', name: 'AI 탐지', icon: <MapTrifold size={18} /> },
  { id: 'illegal', name: '무허가 관리', icon: <ShieldWarning size={18} /> },
  { id: 'permits', name: '허가 데이터', icon: <FileText size={18} /> },
  { id: 'stats', name: '통계', icon: <ChartBar size={18} /> },
];

export default function UnifiedDashboard() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('timeseries');

  const [permitStats, setPermitStats] = useState<SolarPermitStats | null>(null);
  const [matchingStats, setMatchingStats] = useState<MatchingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);
  // 통계 조회 시각 — 매칭 통계는 이 시점 기준 라이브 값임을 화면에 표기(StatsTab)
  const [statsFetchedAt, setStatsFetchedAt] = useState<Date | null>(null);

  // silent: 이미 데이터가 있는 상태의 재조회(탭 진입·탐지 완료 후) — 화면을 로딩으로
  // 갈아치우지 않고 조용히 숫자만 갱신한다. 최초 로드만 로딩 상태 사용.
  const fetchStats = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setStatsLoading(true);
    setStatsError(null);

    const [permitResult, matchingResult] = await Promise.all([
      apiClient.get<SolarPermitStats>('/api/solar-permits/stats'),
      apiClient.get<MatchingStats>('/api/matching/stats'),
    ]);

    let firstError: string | null = null;

    if (isApiSuccess(permitResult)) {
      setPermitStats(permitResult.data);
    } else {
      firstError = permitResult.error.message;
    }

    if (isApiSuccess(matchingResult)) {
      setMatchingStats(matchingResult.data);
    } else if (!firstError) {
      firstError = matchingResult.error.message;
    }

    setStatsError(firstError);
    if (!firstError) setStatsFetchedAt(new Date());
    setStatsLoading(false);
  }, []);

  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.push('/login');
      return;
    }
    setToken(storedToken);
    fetchStats();
  }, [router, fetchStats]);

  // 통계는 실시간이 아니라 시점 갱신: 통계·허가·무허가 관리 탭 진입 시 조용히 재조회.
  // (허가 발전소 수는 정적에 가깝지만, 무허가 의심 수는 탐지 실행으로 변한다)
  useEffect(() => {
    if (activeTab === 'stats' || activeTab === 'permits' || activeTab === 'illegal') {
      fetchStats({ silent: true });
    }
  }, [activeTab, fetchStats]);

  const handleLogout = () => {
    // 인증 토큰만 제거 — localStorage.clear()/sessionStorage.clear() 전체 삭제 금지(FR-101)
    removeLocalStorage('token');
    removeSessionStorage('token');
    router.push('/login');
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <LoadingState size="lg" />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">태양광 패널 통합 모니터링 시스템</h1>
            <p className="text-sm text-slate-400 mt-1">VQ Clustering + AI Detection + Public Data Integration</p>
          </div>

          <div className="flex items-center">
            {permitStats && (
              <div className="text-right mr-6">
                <p className="text-xs text-slate-400">허가 발전소</p>
                <p className="text-lg font-bold text-green-400 mt-0.5">{permitStats.total.toLocaleString()}건</p>
              </div>
            )}
            {matchingStats && (
              <div className="text-right mr-6">
                <p className="text-xs text-slate-400">무허가 의심</p>
                <p className="text-lg font-bold text-red-400 mt-0.5">{(matchingStats.illegal_panels ?? 0).toLocaleString()}건</p>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="inline-flex items-center px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              <SignOut size={18} className="mr-1.5" />
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <TabNav tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />

      <div className="flex-1 overflow-hidden relative">
        {activeTab === 'timeseries' && <TimeSeriesTab />}

        {activeTab === 'detect' && (
          // AI 탐지 완료 직후 헤더/통계 숫자 갱신 — "방금 탐지했는데 숫자가 그대로"인
          // stale 상태 방지 (전면 로딩 없이 조용히)
          <AiDetectionTab onStatsRefresh={() => fetchStats({ silent: true })} />
        )}

        {activeTab === 'illegal' && <IllegalDbTab matchingStats={matchingStats} />}

        {activeTab === 'permits' && (
          <PermitsTab
            stats={permitStats}
            statsLoading={statsLoading}
            statsError={statsError}
            onRetryStats={fetchStats}
          />
        )}

        {activeTab === 'stats' && (
          <StatsTab
            permitStats={permitStats}
            matchingStats={matchingStats}
            loading={statsLoading}
            error={statsError}
            onRetry={fetchStats}
            fetchedAt={statsFetchedAt}
          />
        )}
      </div>
    </div>
  );
}
