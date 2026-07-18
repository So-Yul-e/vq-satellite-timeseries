/**
 * MapView — 05_design-common-system.md 계약
 * DetectionMap.tsx / Map/DashboardMap.tsx / MapViewer.tsx 3곳 중복을 단일 컴포넌트로 통합.
 * Leaflet 아이콘 버전은 단일 버전(1.9.4)으로 고정, 마커 아이콘 로직은 이 파일 1곳에만 존재.
 *
 * States:
 * - Loading: 지도 프레임은 유지, 스피너 오버레이만 표시
 * - Error: 지도 위 ErrorBanner + 이전 마커 상태 보존 (마커는 그대로 렌더링)
 * - Empty: 마커 0건이어도 지도 자체는 정상 렌더링 (빈 상태 안내 없음)
 */

import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polygon, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import L, { Icon } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { MapMarker, MarkerStatus } from '@/types/api';
import ErrorBanner from './ErrorBanner';

// 단일 버전 Leaflet 기본 아이콘 (3곳 중복 해소 — cdnjs 1.9.4로 고정)
const DEFAULT_ICON = new Icon({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

// 판정 상태별 마커 색상 (FR-502) — StatusBadge와 동일 semantic 토큰 사용
const STATUS_COLOR: Record<MarkerStatus, string> = {
  illegal: '#ef4444', // red-500
  legal: '#22c55e', // green-500
  review: '#eab308', // yellow-500
  pending: '#eab308', // yellow-500 — 매칭 미확인(백엔드 실응답 값, 누락 시 투명 마커가 되던 문제 교정)
  permit: '#10b981', // emerald-500 (허가 데이터 오버레이)
};

const STATUS_LABEL: Record<MarkerStatus, string> = {
  illegal: '무허가 의심',
  legal: '합법',
  review: '검토 필요',
  pending: '미확인',
  permit: '허가 시설',
};

function coloredDivIcon(status: MarkerStatus): L.DivIcon {
  const color = STATUS_COLOR[status];
  return L.divIcon({
    className: '',
    html: `<div style="background-color:${color};width:22px;height:22px;border-radius:50%;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.35);"></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

interface LatLng {
  lat: number;
  lng: number;
}

function ViewSync({ center, zoom }: { center?: LatLng; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (!center) return;
    const current = map.getCenter();
    const dist = map.distance([center.lat, center.lng], current);
    const zoomDiff = Math.abs(map.getZoom() - (zoom ?? map.getZoom()));
    // 임계값 100m: 구 5000m에서는 근거리 목록 항목을 클릭해도 지도가 안 움직였음.
    // moveend가 상태를 지도 실제 중심으로 동기화하므로(dist≈0) 사용자 pan과는
    // 충돌하지 않는다 — 프로그램적 setCenter만 이 조건을 넘는다.
    if (dist > 100 || zoomDiff > 1.5) {
      map.flyTo([center.lat, center.lng], zoom ?? map.getZoom(), { duration: 1.2 });
    }
  }, [center?.lat, center?.lng, zoom, map]);
  return null;
}

export interface ViewBounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

function ViewChangeListener({
  onViewChange,
  onMapClick,
}: {
  onViewChange?: (lat: number, lng: number, zoom: number, bounds?: ViewBounds) => void;
  onMapClick?: (lat: number, lng: number) => void;
}) {
  const map = useMapEvents({
    // 지도 클릭 — VQ 분석 지점 지정 등 호출부가 필요할 때만 전달됨
    click: (e) => {
      onMapClick?.(e.latlng.lat, e.latlng.lng);
    },
    moveend: (e) => {
      const m = e.target;
      const c = m.getCenter();
      const b = m.getBounds();
      onViewChange?.(c.lat, c.lng, m.getZoom(), {
        north: b.getNorth(),
        south: b.getSouth(),
        east: b.getEast(),
        west: b.getWest(),
      });
    },
  });

  // 마운트 직후 초기 뷰포트도 1회 콜백 — moveend는 사용자가 지도를 움직여야만 발생하므로
  // 조작 없이 토글만 켠 경우 bounds가 계속 null로 남는 것을 방지 (FR-502)
  useEffect(() => {
    const c = map.getCenter();
    const b = map.getBounds();
    onViewChange?.(c.lat, c.lng, map.getZoom(), {
      north: b.getNorth(),
      south: b.getSouth(),
      east: b.getEast(),
      west: b.getWest(),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

// GEE XYZ 타일 오버레이(위치 기반 시계열 변화탐지 결과) — url은 {z}/{x}/{y} 포함
export interface TileOverlay {
  url: string;
  opacity?: number;
}

export interface MapViewProps {
  markers: MapMarker[];
  center?: LatLng;
  zoom?: number;
  permitOverlay?: boolean;
  tileOverlays?: TileOverlay[];
  // 분석 예정 영역(위치 기반 시계열) — [lat,lng] 코너 목록을 점선 사각형으로 표시
  aoiFootprint?: [number, number][];
  // 사용자가 지도 클릭으로 지정한 분석 지점 — 크로스헤어 마커 + 좌표 라벨 표시
  anchorPoint?: { lat: number; lng: number } | null;
  onMapClick?: (lat: number, lng: number) => void;
  onMarkerClick?: (marker: MapMarker) => void;
  onViewChange?: (lat: number, lng: number, zoom: number, bounds?: ViewBounds) => void;
  variant?: 'nationwide' | 'permits' | 'matching';
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export default function MapView({
  markers,
  center,
  zoom = 7,
  permitOverlay = true,
  tileOverlays,
  aoiFootprint,
  anchorPoint,
  onMapClick,
  onMarkerClick,
  onViewChange,
  loading,
  error,
  onRetry,
}: MapViewProps) {
  const visibleMarkers = permitOverlay ? markers : markers.filter((m) => m.status !== 'permit');

  // 마운트별 고유 key — 탭 전환/재출현 시 이전 Leaflet 인스턴스가 붙은 div를 재사용하다
  // "Map container is already initialized"로 터지는 문제 방지 (매번 새 DOM 노드 보장).
  // 최초 1회만 생성되어 리렌더로 지도가 재생성되지는 않는다.
  const [mapKey] = useState(() => `map-${Math.random().toString(36).slice(2)}`);

  return (
    <div className="absolute inset-0 h-full w-full">
      <MapContainer
        key={mapKey}
        center={[center?.lat ?? 36.5, center?.lng ?? 127.5]}
        zoom={zoom}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap"
        />

        {/* GEE 시계열 오버레이(과거/현재 위성 + 변화 영역) — base 위에 순서대로 */}
        {tileOverlays?.map((o, i) => (
          <TileLayer key={`ov-${i}-${o.url}`} url={o.url} opacity={o.opacity ?? 1} />
        ))}

        {/* 분석 예정 영역 — 점선 사각형(무엇이 분석될지 실행 전에 명확히).
            색은 fuchsia-600: 밝은 OSM 타일에서 indigo-400이 묻히던 문제 교정 +
            지도 의미색(빨강=무허가·초록=허가·노랑=검토·빨강 오버레이=변화)과 비충돌 */}
        {aoiFootprint && aoiFootprint.length >= 3 && (
          <Polygon
            positions={aoiFootprint}
            pathOptions={{ color: '#c026d3', weight: 3, dashArray: '8 6', fill: false }}
          />
        )}

        {/* 분석 지점 마커 — 지도 클릭으로 지정된 좌표를 크로스헤어 + 좌표 라벨로 표시 */}
        {anchorPoint && (
          <Marker
            position={[anchorPoint.lat, anchorPoint.lng]}
            icon={L.divIcon({
              className: '',
              html: '<div style="width:18px;height:18px;border-radius:50%;border:3px solid #c026d3;background:rgba(192,38,211,0.25);box-shadow:0 0 0 2px rgba(255,255,255,0.85);"></div>',
              iconSize: [18, 18],
              iconAnchor: [9, 9],
            })}
          >
            <Tooltip permanent direction="top" offset={[0, -12]} className="text-xs font-bold">
              분석 지점 {anchorPoint.lat.toFixed(4)}, {anchorPoint.lng.toFixed(4)}
            </Tooltip>
          </Marker>
        )}

        {center && <ViewSync center={center} zoom={zoom} />}
        <ViewChangeListener onViewChange={onViewChange} onMapClick={onMapClick} />

        {visibleMarkers.map((marker) => (
          <React.Fragment key={marker.id}>
            {marker.polygon && (
              <Polygon
                positions={marker.polygon as [number, number][]}
                pathOptions={{
                  color: STATUS_COLOR[marker.status],
                  fillColor: STATUS_COLOR[marker.status],
                  fillOpacity: 0.25,
                  weight: 2,
                }}
                eventHandlers={{
                  click: () => onMarkerClick?.(marker),
                }}
              >
                <Tooltip sticky direction="top" className="text-xs font-bold">
                  {marker.label ?? STATUS_LABEL[marker.status]}
                </Tooltip>
              </Polygon>
            )}
            <Marker
              position={[marker.latitude, marker.longitude]}
              icon={coloredDivIcon(marker.status)}
              eventHandlers={{
                click: () => onMarkerClick?.(marker),
              }}
            >
              <Popup>
                <div className="text-sm">
                  <p className="font-bold mb-1">{marker.label ?? STATUS_LABEL[marker.status]}</p>
                  <p className="text-xs text-slate-600">
                    {marker.latitude.toFixed(4)}, {marker.longitude.toFixed(4)}
                  </p>
                </div>
              </Popup>
            </Marker>
          </React.Fragment>
        ))}
      </MapContainer>

      {/* 마커 범례 — 지금 지도에 실제로 떠 있는 종류만 표시. 빨강/초록이 뭔지
          화면 어디에도 없어 헷갈리던 문제 해소 (색·라벨의 단일 소스는 이 파일) */}
      {visibleMarkers.length > 0 && (
        <div className="absolute bottom-4 left-4 z-[500] bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2.5 shadow-lg">
          {(['illegal', 'legal', 'review', 'pending', 'permit'] as MarkerStatus[])
            .filter((s) => visibleMarkers.some((m) => m.status === s))
            .map((s, i) => (
              <p key={s} className={`flex items-center text-xs text-slate-300 ${i === 0 ? '' : 'mt-1.5'}`}>
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full mr-1.5 border border-white/60"
                  style={{ backgroundColor: STATUS_COLOR[s] }}
                />
                {STATUS_LABEL[s]}
                {s === 'permit' && <span className="text-slate-400 ml-1">(참고용 허가 DB)</span>}
              </p>
            ))}
        </div>
      )}

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/40 pointer-events-none z-[500]">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-400" />
        </div>
      )}

      {error && (
        <div className="absolute top-4 left-4 right-4 z-[500]">
          <ErrorBanner message={error} onRetry={onRetry ?? (() => {})} variant="banner" />
        </div>
      )}
    </div>
  );
}
