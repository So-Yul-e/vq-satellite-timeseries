/**
 * 통계 탭 — 02 IA 38~41행, 04 FRD FR-502(부속)
 * permitStats/matchingStats 로드 완료 전까지 로딩, 실패 시 에러 상태(무한 스피너 금지).
 * 2026-07-12 4탭→3탭 재편: 구 "무허가 의심" 탭(MatchingTab)의 매칭 통계 요약(38-1)을 흡수.
 */

'use client';

import type { MatchingStats, SolarPermitStats } from '@/types/api';
import LoadingState from '@/components/common/LoadingState';
import ErrorBanner from '@/components/common/ErrorBanner';
import StatCard from '@/components/common/StatCard';
import { formatDateTime } from './shared';

interface StatsTabProps {
  permitStats: SolarPermitStats | null;
  matchingStats: MatchingStats | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  // 통계가 언제 조회된 값인지 — 탭 진입 시 silent 재조회되므로 그 시각
  fetchedAt: Date | null;
}

export default function StatsTab({ permitStats, matchingStats, loading, error, onRetry, fetchedAt }: StatsTabProps) {
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <LoadingState size="lg" label="통계 불러오는 중..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center px-6">
        <div className="max-w-md w-full">
          <ErrorBanner message={error} onRetry={onRetry} variant="banner" />
        </div>
      </div>
    );
  }

  if (!permitStats) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-slate-400 text-sm">표시할 통계 데이터가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-slate-900">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* 시점 기준 — 매칭 통계는 조회 시점 라이브, 허가 통계는 마지막 임포트 스냅샷.
            두 데이터의 갱신 성격이 달라 시각을 각각 명시(오인 방지) */}
        <div className="flex flex-wrap items-center text-xs text-slate-400 -mr-4">
          <span className="mr-4">
            매칭 통계 기준: <span className="text-slate-200">{fetchedAt ? formatDateTime(fetchedAt) : '—'}</span> (조회 시점)
          </span>
          <span className="mr-4">
            허가 데이터 기준: <span className="text-slate-200">{permitStats.data_as_of ? formatDateTime(permitStats.data_as_of) : '—'}</span> (마지막 임포트)
          </span>
        </div>

        {/* 매칭 통계 요약 (38-1, 구 무허가 의심 탭에서 이관) */}
        <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
          <h3 className="text-xl font-bold text-white mb-4">매칭 통계</h3>
          <div className="flex flex-wrap -mr-4 -mb-4">
            <div className="w-1/4 pr-4 pb-4">
              <StatCard label="무허가 의심" value={matchingStats?.illegal_panels ?? null} unit="건" tone="illegal" />
            </div>
            <div className="w-1/4 pr-4 pb-4">
              <StatCard label="합법 확인" value={matchingStats?.legal_panels ?? null} unit="건" tone="legal" />
            </div>
            <div className="w-1/4 pr-4 pb-4">
              <StatCard label="정확 매칭" value={matchingStats?.exact_matches ?? null} unit="건" />
            </div>
            <div className="w-1/4 pr-4 pb-4">
              <StatCard label="근처 매칭" value={matchingStats?.nearby_matches ?? null} unit="건" />
            </div>
          </div>
        </div>

        {/* 전체 요약 */}
        <div className="flex flex-wrap -mr-4">
          <div className="w-1/4 pr-4">
            <StatCard
              label="전체 허가 발전소"
              value={permitStats.total.toLocaleString()}
              trend={`+${permitStats.with_coordinates.toLocaleString()} 좌표 있음`}
            />
          </div>
          <div className="w-1/4 pr-4">
            <StatCard
              label="총 설비 용량"
              value={(permitStats.total_capacity_kw / 1000000).toFixed(2)}
              unit="GW"
              tone="info"
              trend={`평균 ${permitStats.avg_capacity_kw.toFixed(0)} kW`}
            />
          </div>
          <div className="w-1/4 pr-4">
            <StatCard
              label="무허가 의심"
              value={matchingStats?.illegal_panels ?? null}
              tone="illegal"
              trend="자동 탐지 결과"
            />
          </div>
          <div className="w-1/4 pr-4">
            <StatCard
              label="합법 확인"
              value={matchingStats?.legal_panels ?? null}
              tone="legal"
              trend="매칭 완료"
            />
          </div>
        </div>

        {/* 상위 기관 */}
        <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
          <h3 className="text-xl font-bold text-white mb-4">상위 10개 기관</h3>
          {permitStats.top_institutions && permitStats.top_institutions.length > 0 ? (
            <div className="space-y-3">
              {permitStats.top_institutions.map((inst, index) => (
                <div key={inst.name} className="flex items-center justify-between">
                  <div className="flex items-center flex-1">
                    {/* #1~#9(1자리)와 #10(2자리) 폭이 달라 기관명 시작 위치가 어긋나던 것을
                        고정 폭(inline-block w-10)으로 맞춤 */}
                    <span className="text-2xl font-bold text-slate-600 mr-3 inline-block w-10 text-right">
                      #{index + 1}
                    </span>
                    <div>
                      <p className="text-white font-medium">{inst.name}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{inst.count}개 발전소</p>
                    </div>
                  </div>
                  <p className="text-lg font-bold text-blue-400">{(inst.total_capacity / 1000).toFixed(1)} MW</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">데이터 없음</p>
          )}
        </div>

        {/* 연도별 설치 현황 */}
        <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
          <h3 className="text-xl font-bold text-white mb-4">연도별 설치 현황 (최근 10년)</h3>
          {permitStats.by_year && Object.keys(permitStats.by_year).length > 0 ? (
            <div className="flex flex-wrap -mr-3 -mb-3">
              {Object.entries(permitStats.by_year).map(([year, count]) => (
                <div key={year} className="w-1/5 pr-3 pb-3">
                  <div className="bg-slate-700/60 p-4 rounded text-center">
                    <p className="text-sm text-slate-400">{year}년</p>
                    <p className="text-2xl font-bold text-white mt-1">{count.toLocaleString()}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">데이터 없음</p>
          )}
        </div>
      </div>
    </div>
  );
}
