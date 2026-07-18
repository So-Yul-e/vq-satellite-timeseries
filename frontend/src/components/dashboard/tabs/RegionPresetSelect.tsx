/**
 * RegionPresetSelect — 지역 프리셋 드롭다운 (시계열·AI 탐지 탭 공유)
 *
 * 용도: 실측 좌표 프리셋(shared.ts REGION_PRESETS)을 골라 지도를 해당 지역으로 이동.
 * 선택 시 onSelect(lat, lng, zoom) 콜백만 호출 — 지도 상태 소유는 호출부(각 탭).
 *
 * 계약:
 * - 프리셋 목록의 단일 소스는 shared.ts REGION_PRESETS (여기서 임의 추가 금지 —
 *   좌표는 DB 클러스터링 실측 기반이어야 함, 04 FRD 필드 검증 규칙)
 * - defaultValue="" + disabled placeholder로 "지역 선택" 안내 유지
 */

'use client';

import { REGION_PRESETS } from './shared';

interface RegionPresetSelectProps {
  onSelect: (lat: number, lng: number, zoom: number) => void;
}

export default function RegionPresetSelect({ onSelect }: RegionPresetSelectProps) {
  return (
    <div>
      <label className="block text-xs font-bold text-slate-400 uppercase mb-1">지역 프리셋</label>
      <select
        className="w-full text-sm bg-slate-900 border border-slate-600 rounded px-3 py-2 text-white"
        defaultValue=""
        onChange={(e) => {
          const region = REGION_PRESETS.find((r) => r.name === e.target.value);
          if (region) onSelect(region.lat, region.lng, region.zoom);
        }}
      >
        <option value="" disabled>
          지역 선택
        </option>
        {REGION_PRESETS.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name}
          </option>
        ))}
      </select>
    </div>
  );
}
