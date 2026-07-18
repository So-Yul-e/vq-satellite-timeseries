/**
 * 허가 데이터 탭 — 02 IA 30~33행, 04 FRD FR-502
 * 좌측 필터+리스트 / 우측 지도(MapView permits variant).
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { apiClient, isApiSuccess } from '@/utils/apiClient';
import type { ListResponse, MapMarker, SolarPermit, SolarPermitStats } from '@/types/api';
import LoadingState from '@/components/common/LoadingState';
import ErrorBanner from '@/components/common/ErrorBanner';
import StatCard from '@/components/common/StatCard';
import { formatDateTime } from './shared';

const MapView = dynamic(() => import('@/components/common/MapView'), { ssr: false });

interface PermitsTabProps {
  stats: SolarPermitStats | null;
  statsLoading: boolean;
  statsError: string | null;
  onRetryStats: () => void;
}

interface PermitFilter {
  hasCoordinates: boolean;
  institution: string;
  minCapacity: string;
}

export default function PermitsTab({ stats, statsLoading, statsError, onRetryStats }: PermitsTabProps) {
  const [permits, setPermits] = useState<SolarPermit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<PermitFilter>({
    hasCoordinates: true,
    institution: '',
    minCapacity: '',
  });
  const [selectedCenter, setSelectedCenter] = useState<{ lat: number; lng: number } | null>(null);

  const fetchPermits = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      limit: '100',
      has_coordinates: filter.hasCoordinates ? 'true' : 'false',
    });
    if (filter.institution) params.append('institution_name', filter.institution);
    if (filter.minCapacity && Number(filter.minCapacity) >= 0) {
      params.append('min_capacity', filter.minCapacity);
    }

    const result = await apiClient.get<ListResponse<SolarPermit>>(`/api/solar-permits/?${params}`);
    if (isApiSuccess(result)) {
      setPermits(result.data.items);
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }, [filter]);

  // 필터 변경 시 350ms 디바운스 — 한글 IME로 한 글자씩 칠 때마다 요청이 나가
  // 먼저 보낸 요청이 나중에 도착해 결과가 뒤섞이던 문제(경합) 방지
  useEffect(() => {
    const t = setTimeout(() => {
      fetchPermits();
    }, 350);
    return () => clearTimeout(t);
  }, [fetchPermits]);

  const markers: MapMarker[] = permits
    .filter((p) => p.latitude != null && p.longitude != null)
    .map((p) => ({
      id: p.id,
      latitude: p.latitude as number,
      longitude: p.longitude as number,
      status: 'permit',
      label: p.facility_name,
    }));

  return (
    <div className="h-full flex">
      {/* 사이드패널 전체 스크롤 — 구 구조는 통계+필터가 고정 블록이라 리스트가
          하단 자투리 높이의 좁은 스크롤 띠로 짜부라졌음(다른 탭과 동일 패턴으로 통일) */}
      <div className="w-96 bg-slate-800 border-r border-slate-700 flex flex-col overflow-y-auto">
        {/* 통계 요약 */}
        <div className="p-4 border-b border-slate-700">
          <h3 className="text-white font-semibold mb-1">전체 통계</h3>
          {/* 데이터 기준일 — 공공데이터포털 수동 임포트 스냅샷, 자동 갱신 아님을 명시 */}
          <p className="text-xs text-slate-400">
            {stats?.data_as_of
              ? `데이터 기준: ${formatDateTime(stats.data_as_of)} 수동 임포트 (자동 갱신 없음)`
              : '데이터 기준 시각 정보 없음'}
          </p>
          {/* 자동 동기화 정보 — 필드가 있을 때만 렌더(백엔드 동시 작업, 옵셔널 안전 처리) */}
          {stats?.last_sync_at && (
            <p className="text-xs text-slate-400">
              마지막 자동 동기화: {formatDateTime(stats.last_sync_at)}
            </p>
          )}
          {stats?.last_sync_status === 'failed' && (
            <p className="text-xs text-red-400">최근 동기화 실패</p>
          )}
          <div className="mb-3" />
          {statsError ? (
            <ErrorBanner message={statsError} onRetry={onRetryStats} variant="inline" />
          ) : (
            <div className="flex flex-wrap -mr-3 -mb-3">
              <div className="w-1/2 pr-3 pb-3">
                <StatCard label="전체" value={stats?.total ?? null} loading={statsLoading} />
              </div>
              <div className="w-1/2 pr-3 pb-3">
                <StatCard label="좌표 있음" value={stats?.with_coordinates ?? null} tone="legal" loading={statsLoading} />
              </div>
              <div className="w-1/2 pr-3 pb-3">
                <StatCard
                  label="총 용량"
                  value={stats ? (stats.total_capacity_kw / 1000000).toFixed(1) : null}
                  unit="GW"
                  tone="info"
                  loading={statsLoading}
                />
              </div>
              <div className="w-1/2 pr-3 pb-3">
                <StatCard
                  label="평균 용량"
                  value={stats ? stats.avg_capacity_kw.toFixed(0) : null}
                  unit="kW"
                  loading={statsLoading}
                />
              </div>
            </div>
          )}
        </div>

        {/* 필터 */}
        <div className="p-4 border-b border-slate-700 space-y-3">
          <h3 className="text-white font-semibold">필터</h3>
          <label className="flex items-center text-sm text-slate-300">
            <input
              type="checkbox"
              checked={filter.hasCoordinates}
              onChange={(e) => setFilter({ ...filter, hasCoordinates: e.target.checked })}
              className="mr-2"
            />
            좌표 있는 데이터만
          </label>
          <input
            type="text"
            placeholder="기관명 검색..."
            value={filter.institution}
            onChange={(e) => setFilter({ ...filter, institution: e.target.value })}
            className="w-full px-3 py-2 bg-slate-750 bg-slate-700 text-white rounded border border-slate-600 text-sm"
          />
          <input
            type="number"
            min={0}
            placeholder="최소 용량 (kW)"
            value={filter.minCapacity}
            onChange={(e) => setFilter({ ...filter, minCapacity: e.target.value })}
            className="w-full px-3 py-2 bg-slate-700 text-white rounded border border-slate-600 text-sm"
          />
        </div>

        {/* 리스트 — 패널 전체 스크롤에 합류(내부 개별 스크롤 제거) */}
        <div className="flex-1 p-4 space-y-2">
          {loading ? (
            <LoadingState size="md" />
          ) : error ? (
            <ErrorBanner message={error} onRetry={fetchPermits} variant="inline" />
          ) : permits.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">조건에 맞는 허가 데이터가 없습니다.</p>
          ) : (
            <>
              {permits.map((permit) => (
                <button
                  key={permit.id}
                  type="button"
                  onClick={() =>
                    permit.latitude != null && permit.longitude != null
                      ? setSelectedCenter({ lat: permit.latitude, lng: permit.longitude })
                      : undefined
                  }
                  className="w-full text-left bg-slate-700/60 p-3 rounded hover:bg-slate-700 cursor-pointer transition-colors"
                >
                  <h4 className="text-white font-medium text-sm mb-1">{permit.facility_name ?? '이름 없음'}</h4>
                  <p className="text-xs text-slate-400 mb-2">{permit.road_address || permit.lot_address || '주소 정보 없음'}</p>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">{permit.institution_name}</span>
                    {permit.capacity && <span className="text-green-400 font-medium">{permit.capacity} kW</span>}
                  </div>
                </button>
              ))}
              {/* ST-L1: limit=100 상한 도달 시 절단 무고지 방지 — 정확한 전체 매칭 수는
                  응답에 없으므로(count 미제공) "100건 상한 도달" 형태로만 안내 */}
              {permits.length === 100 && (
                <p className="text-xs text-yellow-500 text-center pt-2">
                  상위 100건만 표시 — 필터로 범위를 좁혀주세요
                </p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex-1 relative">
        <MapView markers={markers} center={selectedCenter ?? undefined} zoom={selectedCenter ? 14 : 7} variant="permits" />
      </div>
    </div>
  );
}
