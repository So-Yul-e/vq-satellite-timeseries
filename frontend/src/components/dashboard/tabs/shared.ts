/**
 * 대시보드 탭 공유 유틸 — 2026-07-17 기능별 탭 분리 재편(02 IA 21행)으로
 * 구 DetectionMapTab에 있던 공용 로직을 분리. 마커 변환·지역 프리셋·위험도 조회 훅.
 */

import { useCallback, useEffect, useState } from 'react';
import { apiClient, isApiSuccess } from '@/utils/apiClient';
import type { DetectedPanel, IllegalPanel, MapMarker, RiskAssessment, SolarPermit } from '@/types/api';

/**
 * 날짜+시간 공통 포맷 (ko-KR, 분 단위) — "2026. 07. 17. 14:32" 형태.
 * 백엔드 datetime은 UTC('Z' 표기, solar_panel.to_dict 참조)로 내려오고
 * Date/toLocaleString이 브라우저 로컬(KST)로 변환한다. 초는 표시하지 않는다.
 */
export function formatDateTime(value: string | Date): string {
  const d = typeof value === 'string' ? new Date(value) : value;
  return d.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// 04 FRD 필드 검증 규칙: 실제 태양광 밀집지 실측 좌표만 사용 (2026-07-12 재검증)
export const REGION_PRESETS = [
  { name: '전남 무안', lat: 34.83, lng: 126.4, zoom: 11 },
  { name: '전남 목포', lat: 34.7544, lng: 126.3566, zoom: 12 },
  { name: '전북 부안', lat: 35.5701, lng: 126.6875, zoom: 12 },
  { name: '충남 논산', lat: 36.1502, lng: 127.0734, zoom: 12 },
];

export function panelToMarker(panel: DetectedPanel): MapMarker {
  return {
    id: panel.id,
    latitude: panel.latitude,
    longitude: panel.longitude,
    status: panel.permit_status,
    label: `면적 ${(panel.area ?? panel.area_m2 ?? 0).toFixed(0)}m² · 신뢰도 ${(panel.confidence * 100).toFixed(0)}%`,
    panel,
  };
}

export function illegalToDetectedPanel(p: IllegalPanel): DetectedPanel {
  return {
    id: p.id,
    detection_id: p.detection_id,
    latitude: p.latitude,
    longitude: p.longitude,
    area: p.area_m2 ?? 0,
    area_m2: p.area_m2,
    confidence: p.confidence,
    permit_status: 'illegal',
    detection_date: p.detection_date,
    permit_info: p.permit_info,
  };
}

export function permitToMarker(permit: SolarPermit): MapMarker | null {
  if (permit.latitude === undefined || permit.longitude === undefined) return null;
  return {
    id: `permit-${permit.id}`,
    latitude: permit.latitude,
    longitude: permit.longitude,
    status: 'permit',
    label: permit.facility_name,
  };
}

/**
 * 위험도 평가 조회 훅 (FR-205) — 패널 선택 시 기존 평가 조회, 없으면 새로 실행.
 * AI 탐지 탭·무허가 관리 탭이 공유(팝업 부분 실패 원칙: 위험도 실패해도 팝업은 뜬다).
 */
export function useRiskAssessment(selectedPanelId: string | undefined) {
  const [riskAssessment, setRiskAssessment] = useState<RiskAssessment | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  const fetchRiskAssessment = useCallback(async (panelId: string) => {
    setRiskLoading(true);
    setRiskError(null);
    setRiskAssessment(null);

    const existing = await apiClient.get<RiskAssessment>(`/api/risk/panels/${panelId}/risk`);
    if (isApiSuccess(existing)) {
      setRiskAssessment(existing.data);
      setRiskLoading(false);
      return;
    }

    const fresh = await apiClient.post<RiskAssessment>(`/api/risk/panels/${panelId}/assess`, {});
    if (isApiSuccess(fresh)) {
      setRiskAssessment(fresh.data);
    } else {
      setRiskError(fresh.error.message);
    }
    setRiskLoading(false);
  }, []);

  useEffect(() => {
    if (selectedPanelId) {
      fetchRiskAssessment(selectedPanelId);
    } else {
      setRiskAssessment(null);
      setRiskError(null);
    }
  }, [selectedPanelId, fetchRiskAssessment]);

  return { riskAssessment, riskLoading, riskError };
}
