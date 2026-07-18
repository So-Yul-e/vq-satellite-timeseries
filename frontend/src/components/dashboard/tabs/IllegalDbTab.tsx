/**
 * 무허가 관리 탭 — 과거 탐지가 누적된 무허가 의심 DB 조회/관리 (02 IA 21행 2026-07-17 재편, FR-202)
 * AI 탐지의 "이번 결과"와 다른 여정(누적 데이터 브라우징)이라 전용 탭으로 분리.
 * 목록 클릭 → 지도 이동 + 상세 팝업(위험도 포함). 매칭 통계 요약 상단 표시.
 * mock 데이터 렌더링 금지 — 서버 응답만 렌더링(FR-501).
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ArrowsClockwise } from '@phosphor-icons/react';
import { apiClient, isApiSuccess } from '@/utils/apiClient';
import type { DetectedPanel, IllegalPanel, ListResponse, MapMarker, MatchingStats } from '@/types/api';
import PanelDetailPopup from '@/components/common/PanelDetailPopup';
import ErrorBanner from '@/components/common/ErrorBanner';
import LoadingState from '@/components/common/LoadingState';
import MiniStatCards from '@/components/common/MiniStatCards';
import { formatDateTime, illegalToDetectedPanel, useRiskAssessment } from './shared';

const MapView = dynamic(() => import('@/components/common/MapView'), { ssr: false });

interface IllegalDbTabProps {
  matchingStats: MatchingStats | null;
}

export default function IllegalDbTab({ matchingStats }: IllegalDbTabProps) {
  const [center, setCenter] = useState({ lat: 36.5, lng: 127.5 });
  const [zoom, setZoom] = useState(7);
  const [illegalPanels, setIllegalPanels] = useState<IllegalPanel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 목록이 언제 기준의 데이터인지 명시 — "저건 언제 업데이트 되는 거야?"에 화면이 답하게
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [selectedPanel, setSelectedPanel] = useState<DetectedPanel | null>(null);
  const { riskAssessment, riskLoading, riskError } = useRiskAssessment(selectedPanel?.id);

  const fetchIllegalPanels = useCallback(async () => {
    setLoading(true);
    setError(null);
    const result = await apiClient.get<ListResponse<IllegalPanel>>('/api/matching/illegal-panels?limit=50');
    if (isApiSuccess(result)) {
      setIllegalPanels(result.data.items);
      setFetchedAt(new Date());
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }, []);

  // 탭 진입 시 1회 조회 (length 조건 재조회 금지 — 무한 루프 이력, 재시도는 수동 버튼)
  useEffect(() => {
    fetchIllegalPanels();
  }, [fetchIllegalPanels]);

  const handleSelect = (p: IllegalPanel) => {
    setSelectedPanel(illegalToDetectedPanel(p));
    // 상세 패널(우측 384px, PanelDetailPopup w-96)이 지도 우측을 덮으므로
    // 전체 지도 중앙에 놓으면 마커가 패널 뒤에 가려진다 — 마커가 "보이는 영역"의
    // 중앙에 오도록 지도 중심을 패널 절반 폭만큼 동쪽으로 보정.
    // (web mercator 경도/px = 360 / (256 · 2^zoom), 위도와 무관)
    const zoom = 15;
    const POPUP_WIDTH_PX = 384;
    const lngOffset = (POPUP_WIDTH_PX / 2) * (360 / (256 * Math.pow(2, zoom)));
    setCenter({ lat: p.latitude, lng: p.longitude + lngOffset });
    setZoom(zoom);
  };

  const markers: MapMarker[] = illegalPanels.map((p) => ({
    id: p.id,
    latitude: p.latitude,
    longitude: p.longitude,
    status: 'illegal',
    panel: illegalToDetectedPanel(p),
  }));

  return (
    <div className="h-full flex">
      {/* 사이드패널 — 매칭 요약 + 누적 목록 */}
      <div className="w-96 bg-slate-800 border-r border-slate-700 flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-slate-700">
          <label className="block text-xs font-bold text-slate-400 uppercase mb-2">매칭 현황</label>
          {/* 매칭 요약 — 공통 MiniStatCards (null=미로딩 "—", 0건은 0으로 구분 표시) */}
          <MiniStatCards
            items={[
              { label: '무허가 의심', count: matchingStats?.illegal_panels ?? null, tone: 'text-red-400' },
              { label: '합법 확인', count: matchingStats?.legal_panels ?? null, tone: 'text-green-400' },
            ]}
          />
          <p className="text-xs text-slate-400 mt-2 leading-snug">
            과거 AI 탐지가 누적된 전국 목록입니다. "무허가 의심"은 매칭되는 허가를
            찾지 못한 상태이지 위법 확정이 아닙니다.
          </p>
        </div>

        <div className="flex-1 p-4">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-white font-semibold text-sm">무허가 의심 시설 목록</h3>
            {/* 새로고침 — 아이콘 버튼(Phosphor, 이모지 금지 규칙). 조회 중엔 회전 */}
            <button
              type="button"
              onClick={fetchIllegalPanels}
              disabled={loading}
              aria-label="목록 새로고침"
              title="목록 새로고침"
              className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-slate-700 disabled:opacity-50 transition-colors"
            >
              <ArrowsClockwise size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
          {/* 목록 기준 시각 — 탭 진입/새로고침 시점의 스냅샷임을 시간까지 명시 */}
          <p className="text-xs text-slate-400 mb-1">
            {fetchedAt
              ? `갱신: ${formatDateTime(fetchedAt)}`
              : '조회 중...'}
          </p>
          {/* ST-M1: 헤더의 matchingStats(전체)와 목록(limit=50)이 절단되어 다를 수 있음을
              고지 — 안 하면 "무허가 50건"으로 오해(실제 169건 중 상위 50건 표시). */}
          {!loading && matchingStats && matchingStats.illegal_panels > illegalPanels.length ? (
            <p className="text-xs text-yellow-500 mb-3">
              전체 {matchingStats.illegal_panels}건 중 상위 {illegalPanels.length}건 표시 (신뢰도순)
            </p>
          ) : (
            <div className="mb-3" />
          )}
          {loading ? (
            <LoadingState size="md" />
          ) : error ? (
            <ErrorBanner message={error} onRetry={fetchIllegalPanels} variant="inline" />
          ) : illegalPanels.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">무허가 의심 시설이 없습니다.</p>
          ) : (
            <div className="space-y-2">
              {illegalPanels.map((panel) => (
                <button
                  key={panel.id}
                  type="button"
                  onClick={() => handleSelect(panel)}
                  className="w-full text-left bg-red-900/10 border border-red-500/30 p-3 rounded hover:bg-red-900/20 cursor-pointer transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="text-white font-medium text-sm">탐지 ID: {panel.detection_id?.slice(0, 8) ?? panel.id.slice(0, 8)}...</h4>
                    <span className="text-xs bg-red-500 text-white px-2 py-1 rounded">무허가 의심</span>
                  </div>
                  <div className="space-y-1.5 text-xs text-slate-300">
                    <p>위치: {panel.latitude.toFixed(4)}, {panel.longitude.toFixed(4)}</p>
                    <p>면적: {panel.area_m2?.toFixed(0) ?? '—'} m²</p>
                    <p>신뢰도: {(panel.confidence * 100).toFixed(1)}%</p>
                    {panel.detection_date && (
                      // 시간까지 표시 — 백엔드가 UTC('Z')로 내려주고 브라우저가 KST로 변환
                      <p>탐지: {formatDateTime(panel.detection_date)}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 지도 — 목록 클릭 시 해당 위치로 이동 */}
      <div className="flex-1 relative">
        <MapView
          markers={markers}
          center={center}
          zoom={zoom}
          onMarkerClick={(marker) => marker.panel && setSelectedPanel(marker.panel)}
          onViewChange={(lat, lng, z) => {
            setCenter({ lat, lng });
            setZoom(z);
          }}
        />
      </div>

      {selectedPanel && (
        <PanelDetailPopup
          panel={riskAssessment ? { ...selectedPanel, risk_assessment: riskAssessment } : selectedPanel}
          onClose={() => setSelectedPanel(null)}
          riskLoading={riskLoading}
          riskError={riskError}
        />
      )}
    </div>
  );
}
