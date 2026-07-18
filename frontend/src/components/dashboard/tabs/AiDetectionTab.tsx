/**
 * AI 탐지 탭 — YOLOv8 태양광 패널 탐지 전용 (02 IA 21행 2026-07-17 재편, FR-201/FR-502)
 * 여정: 지역 선택 → AI 탐지 실행 → 이번 결과 확인 → 허가 오버레이로 대조.
 * 무허가 누적 DB는 "무허가 관리" 탭, VQ 시계열은 "시계열 변화탐지" 탭으로 분리.
 * mock 데이터 렌더링 금지 — 서버 응답만 렌더링(FR-501).
 */

'use client';

import { useCallback, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { apiClient, isApiSuccess } from '@/utils/apiClient';
import type { AnalyzeResponse, DetectedPanel, MapMarker, SolarPermit } from '@/types/api';
import type { ViewBounds } from '@/components/common/MapView';
import PanelDetailPopup from '@/components/common/PanelDetailPopup';
import ErrorBanner from '@/components/common/ErrorBanner';
import ButtonSpinner from '@/components/common/ButtonSpinner';
import MiniStatCards from '@/components/common/MiniStatCards';
import RegionPresetSelect from './RegionPresetSelect';
import { panelToMarker, permitToMarker, useRiskAssessment } from './shared';

const MapView = dynamic(() => import('@/components/common/MapView'), { ssr: false });

const PERMIT_OVERLAY_MAX = 500;
const PERMIT_OVERLAY_DEBOUNCE_MS = 500;

interface AiDetectionTabProps {
  // AI 탐지 완료 후 대시보드 헤더/통계 재조회 트리거 (통계는 시점 갱신 방식)
  onStatsRefresh?: () => void;
}

export default function AiDetectionTab({ onStatsRefresh }: AiDetectionTabProps) {
  const [center, setCenter] = useState({ lat: 36.5, lng: 127.5 });
  const [zoom, setZoom] = useState(7);
  const [bounds, setBounds] = useState<ViewBounds | null>(null);
  const [panels, setPanels] = useState<DetectedPanel[]>([]);
  const [selectedPanel, setSelectedPanel] = useState<DetectedPanel | null>(null);
  const { riskAssessment, riskLoading, riskError } = useRiskAssessment(selectedPanel?.id);

  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  // RB-M1: 탐지를 한 번이라도 성공 실행했는지 추적 — panels.length만으로는
  // "실행해서 0건"과 "아직 실행 안 함"을 구분 못 해 버튼만 원복되고 무피드백이었음
  const [hasAnalyzed, setHasAnalyzed] = useState(false);

  // 허가 데이터 오버레이 (FR-502) — 참고용 배경 데이터
  const [showPermits, setShowPermits] = useState(false);
  const [permitMarkers, setPermitMarkers] = useState<MapMarker[]>([]);
  const [permitLoading, setPermitLoading] = useState(false);
  const [permitError, setPermitError] = useState<string | null>(null);
  const [permitTruncated, setPermitTruncated] = useState(false);
  const permitDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true);
    setAnalyzeError(null);

    const result = await apiClient.post<AnalyzeResponse>('/api/solar/analyze', {
      latitude: center.lat,
      longitude: center.lng,
      buffer_km: 0.5,
      bounds: bounds ?? undefined,
    });

    if (isApiSuccess(result)) {
      setPanels(result.data.detection.panels);
      setHasAnalyzed(true);
      // 탐지가 DB에 영속되므로 무허가 의심 수 등이 변함 — 헤더/통계 조용히 갱신
      onStatsRefresh?.();
    } else {
      setAnalyzeError(result.error.message);
    }
    setAnalyzing(false);
  }, [center, bounds, onStatsRefresh]);

  const fetchPermitOverlay = useCallback(async (b: ViewBounds) => {
    setPermitLoading(true);
    setPermitError(null);

    const centerLat = (b.north + b.south) / 2;
    const centerLng = (b.east + b.west) / 2;
    const latSpanKm = Math.abs(b.north - b.south) * 111.0;
    const lngSpanKm = Math.abs(b.east - b.west) * 88.0;
    const radiusKm = Math.min(Math.max(Math.hypot(latSpanKm, lngSpanKm) / 2, 1), 100);

    const params = new URLSearchParams({
      latitude: String(centerLat),
      longitude: String(centerLng),
      radius_km: String(radiusKm),
      limit: String(PERMIT_OVERLAY_MAX),
    });

    const result = await apiClient.get<{ total: number; items: { permit: SolarPermit }[] }>(
      `/api/solar-permits/nearby?${params}`,
    );

    if (isApiSuccess(result)) {
      const markers = result.data.items
        .map((item) => permitToMarker(item.permit))
        .filter((m): m is MapMarker => m !== null);
      setPermitMarkers(markers);
      setPermitTruncated(result.data.total > markers.length);
    } else {
      setPermitError(result.error.message);
    }
    setPermitLoading(false);
  }, []);

  const handleTogglePermits = (checked: boolean) => {
    setShowPermits(checked);
    if (!checked) {
      setPermitMarkers([]);
      setPermitError(null);
      setPermitTruncated(false);
    } else if (bounds) {
      fetchPermitOverlay(bounds);
    }
  };

  const handleViewChange = useCallback(
    (lat: number, lng: number, z: number, b?: ViewBounds) => {
      setCenter({ lat, lng });
      setZoom(z);
      if (!b) return;
      setBounds(b);

      if (!showPermits) return;
      if (permitDebounceRef.current) clearTimeout(permitDebounceRef.current);
      permitDebounceRef.current = setTimeout(() => {
        fetchPermitOverlay(b);
      }, PERMIT_OVERLAY_DEBOUNCE_MS);
    },
    [showPermits, fetchPermitOverlay],
  );

  // id 중복 방어선 — 서버 응답에 같은 패널이 중복 실려도 React key 충돌 방지
  const markers: MapMarker[] = Array.from(
    new Map([...panels.map(panelToMarker), ...permitMarkers].map((m) => [m.id, m])).values(),
  );

  return (
    <div className="h-full flex">
      {/* 사이드패널 — 서비스 흐름: 지역 → 탐지 실행 → 이번 결과 → 참고 오버레이 */}
      <div className="w-96 bg-slate-800 border-r border-slate-700 flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-slate-700 space-y-3">
          {/* 지역 프리셋 — 공통 컴포넌트(RegionPresetSelect), 지도 상태는 이 탭이 소유 */}
          <RegionPresetSelect
            onSelect={(lat, lng, z) => {
              setCenter({ lat, lng });
              setZoom(z);
            }}
          />

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={analyzing}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 text-white font-bold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center"
          >
            {analyzing && <ButtonSpinner />}
            {analyzing ? 'AI 탐지 중...' : 'AI 탐지 실행'}
          </button>
          {analyzeError && (
            <ErrorBanner message={analyzeError} onRetry={handleAnalyze} variant="inline" />
          )}
        </div>

        {/* 이번 탐지 결과 — 탐지를 실행해 결과가 있을 때만 등장 (progressive disclosure) */}
        {panels.length > 0 && (
          <div className="p-4 border-b border-slate-700">
            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">이번 탐지 결과</label>
            {/* 판정 상태별 요약 — 공통 MiniStatCards (05 semantic 토큰 tone) */}
            <MiniStatCards
              items={[
                { label: '무허가 의심', count: panels.filter((p) => p.permit_status === 'illegal').length, tone: 'text-red-400' },
                { label: '합법', count: panels.filter((p) => p.permit_status === 'legal').length, tone: 'text-green-400' },
                { label: '미확인', count: panels.filter((p) => p.permit_status === 'review' || p.permit_status === 'pending').length, tone: 'text-yellow-400' },
              ]}
            />
            <p className="text-xs text-slate-400 mt-2">지도에 마커로 표시됨 · 마커 클릭 시 상세 정보</p>
          </div>
        )}

        {/* RB-M1: 성공했으나 0건인 상태를 명시 — hasAnalyzed로 "실행 후 0건"과
            "아직 실행 안 함"을 구분(초기 상태에는 렌더 안 함) */}
        {hasAnalyzed && panels.length === 0 && (
          <div className="p-4 border-b border-slate-700">
            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">이번 탐지 결과</label>
            <p className="text-sm text-slate-400">이 영역에서 탐지된 태양광 패널이 없습니다.</p>
          </div>
        )}

        {/* 지도 오버레이 (참고용) — 결과 대조 단계 */}
        <div className="p-4 space-y-2">
          <label className="block text-xs font-bold text-slate-400 uppercase mb-1">지도 오버레이 (참고용)</label>
          <label className="flex items-center text-sm text-slate-300">
            <input
              type="checkbox"
              checked={showPermits}
              onChange={(e) => handleTogglePermits(e.target.checked)}
              className="mr-2"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style={{ backgroundColor: '#10b981' }} />
            허가받은 발전소 위치 (공공 허가 DB)
            {permitLoading && (
              <span className="inline-block h-3 w-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin ml-2" />
            )}
          </label>
          <p className="text-xs text-slate-400 leading-snug">
            탐지 결과와 별개인 배경 데이터입니다. 무허가 의심 마커 주변에 실제 허가
            시설이 있는지 대조할 때 켜세요. 지금 보는 화면 주변만 불러옵니다.
          </p>
          {showPermits && permitTruncated && (
            <p className="text-xs text-yellow-500">
              허가 데이터가 {PERMIT_OVERLAY_MAX}건을 초과해 일부만 표시됩니다. 지도를 확대해 범위를 좁혀주세요.
            </p>
          )}
          {showPermits && permitError && (
            <ErrorBanner
              message={permitError}
              onRetry={() => bounds && fetchPermitOverlay(bounds)}
              variant="inline"
            />
          )}
        </div>
      </div>

      {/* 지도 */}
      <div className="flex-1 relative">
        <MapView
          markers={markers}
          center={center}
          zoom={zoom}
          permitOverlay
          onMarkerClick={(marker) => marker.panel && setSelectedPanel(marker.panel)}
          onViewChange={handleViewChange}
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
