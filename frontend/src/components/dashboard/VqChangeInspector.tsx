/**
 * VqChangeInspector — 변화 후보 인스펙터 (04 FRD 28-3, FR-402)
 *
 * VQ-네이티브 변화 인스펙터(2026-07-18 재설계): 변화 판정은 VQ 코드북(할당 변화)이
 * 하고(changeMask, authoritative), 이 컴포넌트는 그 결과를 탐색하게 한다. 그룹에 의미
 * 라벨을 붙이지 않는다(03 정책 §판정과 조치의 경계 — 비지도라 무엇의 변화인지 모름).
 *
 * - changeMask: VQ 코드워드 할당이 바뀐 패치(=변화)의 1차 게이트
 * - 강도 필터(슬라이더): 판정 아님. VQ 변화 중 CVA 강도 낮은 것을 걸러 보는 보조축
 * - 그룹 토글: 같은 코드워드 전이끼리 묶은 익명 그룹 단위 제외(계절 식생 등)
 * - 강도 상위 목록 / T1·T2 배경 전환: 탐색·검증 보조
 */

'use client';

import { useMemo, useState } from 'react';
import type { VqPatchGrid } from '@/types/api';

// 그룹 색 팔레트(익명 그룹 A/B/C/D) — 의미 없음, 구분용
const GROUP_COLORS = ['#818cf8', '#fbbf24', '#34d399', '#fb7185'];
const GROUP_NAMES = ['A', 'B', 'C', 'D'];

interface VqChangeInspectorProps {
  t1Url: string;
  t2Url: string;
  patchGrid: VqPatchGrid;
  // VQ 판정: 코드워드 할당이 바뀐 패치(=변화)의 authoritative mask. 오버레이/순위의 1차 게이트.
  changeMask: boolean[];
  magnitudes: number[];
  groups: number[];
  serverThreshold: number;
  // YOLO 교차참조로 태양광이 확인된 변화 패치 인덱스(고해상 VWorld+YOLO)
  solarPatches?: number[];
  contextLabel?: string; // 예: "34.8300, 126.4000 · 2019-05-01 → 현재"
  onClose: () => void;
}

export default function VqChangeInspector({
  t1Url,
  t2Url,
  patchGrid,
  changeMask,
  magnitudes,
  groups,
  serverThreshold,
  solarPatches,
  contextLabel,
  onClose,
}: VqChangeInspectorProps) {
  const solarSet = useMemo(() => new Set(solarPatches ?? []), [solarPatches]);
  const [threshold, setThreshold] = useState(serverThreshold);
  const [background, setBackground] = useState<'t1' | 't2'>('t2');
  const [selectedPatch, setSelectedPatch] = useState<number | null>(null);
  const [disabledGroups, setDisabledGroups] = useState<Set<number>>(new Set());

  const { minMag, maxMag } = useMemo(() => {
    if (magnitudes.length === 0) return { minMag: 0, maxMag: 1 };
    return { minMag: Math.min(...magnitudes), maxMag: Math.max(...magnitudes) };
  }, [magnitudes]);

  // 존재하는 그룹 목록(크기순으로 이미 0부터 재부여됨) + 그룹별 패치 수
  const groupCounts = useMemo(() => {
    const counts = new Map<number, number>();
    groups.forEach((g) => {
      if (g >= 0) counts.set(g, (counts.get(g) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => a[0] - b[0]);
  }, [groups]);

  // "보이는" 변화 후보 = VQ 판정(changeMask, 코드워드 할당 변화)이 1차 게이트.
  // 그 위에서 강도 슬라이더(threshold)와 그룹 토글로 좁힌다 — 슬라이더는 판정이
  // 아니라 "VQ가 변화로 본 것 중 강도로 필터"하는 보조축(재설계 2026-07-18).
  const visiblePatches = useMemo(
    () =>
      magnitudes
        .map((m, i) => ({ i, m, g: groups[i] ?? -1 }))
        .filter((p) => (changeMask[p.i] ?? false) && p.m >= threshold && !disabledGroups.has(p.g)),
    [magnitudes, groups, threshold, disabledGroups, changeMask],
  );

  // 강도 상위 목록(토글·threshold 반영, 상위 10)
  const topPatches = useMemo(
    () => [...visiblePatches].sort((a, b) => b.m - a.m).slice(0, 10),
    [visiblePatches],
  );

  const { image_width: W, image_height: H, n_x, patch_size, stride } = patchGrid;

  const patchRect = (idx: number) => {
    const col = idx % n_x;
    const row = Math.floor(idx / n_x);
    const x = col * stride;
    const y = row * stride;
    return { x, y, w: Math.min(patch_size, W - x), h: Math.min(patch_size, H - y) };
  };

  const norm = (m: number) => (maxMag > minMag ? (m - minMag) / (maxMag - minMag) : 1);

  const toggleGroup = (g: number) => {
    setDisabledGroups((prev) => {
      const next = new Set(prev);
      if (next.has(g)) next.delete(g);
      else next.add(g);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-[1000] bg-black/90 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-6xl max-h-[92vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <div>
            <p className="text-white font-bold text-sm">변화 후보 인스펙터</p>
            <p className="text-xs text-slate-400 mt-1">
              {contextLabel ?? '두 시점 비교'} · 후보 {visiblePatches.length}개
              {solarSet.size > 0 && (
                <span className="text-amber-300"> · ☀ 태양광 확인 {solarSet.size}곳(노란 테두리)</span>
              )}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-300 hover:text-white text-sm px-2 py-1">
            닫기 ✕
          </button>
        </div>

        <div className="flex-1 flex min-h-0">
          {/* 좌: 이미지 + SVG 오버레이 */}
          <div className="flex-1 min-w-0 p-4 flex flex-col">
            <div className="flex items-center mb-2">
              {(['t1', 't2'] as const).map((bg, i) => (
                <button
                  key={bg}
                  type="button"
                  onClick={() => setBackground(bg)}
                  className={`text-xs px-3 py-1.5 rounded border transition-colors ${i === 0 ? '' : 'ml-1'} ${
                    background === bg
                      ? 'bg-indigo-600 border-indigo-500 text-white font-bold'
                      : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  {bg === 't1' ? '시점1 (과거)' : '시점2 (현재)'}
                </button>
              ))}
              <p className="text-xs text-slate-400 ml-3">배경을 바꿔가며 같은 자리를 비교해보세요</p>
            </div>

            <div className="relative flex-1 min-h-0 overflow-auto bg-slate-950 rounded border border-slate-700">
              <div className="relative" style={{ aspectRatio: `${W} / ${H}` }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={background === 't1' ? t1Url : t2Url}
                  alt={background === 't1' ? '시점1' : '시점2'}
                  className="absolute inset-0 w-full h-full object-contain"
                />
                <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid meet">
                  {visiblePatches.map(({ i, m, g }) => {
                    const r = patchRect(i);
                    const color = GROUP_COLORS[g % GROUP_COLORS.length] ?? '#818cf8';
                    const selected = selectedPatch === i;
                    const solar = solarSet.has(i);
                    return (
                      <g key={i} onClick={() => setSelectedPatch(selected ? null : i)} style={{ cursor: 'pointer' }}>
                        <rect
                          x={r.x}
                          y={r.y}
                          width={r.w}
                          height={r.h}
                          fill={color}
                          fillOpacity={0.18 + 0.4 * norm(m)}
                          // 태양광 확인 패치는 노란 굵은 테두리로 구분(YOLO 교차참조)
                          stroke={selected ? '#ffffff' : solar ? '#fbbf24' : color}
                          strokeWidth={selected ? 6 : solar ? 5 : 2}
                        >
                          <title>{`패치 #${i} · 강도 ${m.toFixed(1)} · 그룹 ${GROUP_NAMES[g] ?? g}${solar ? ' · 태양광 확인' : ''}`}</title>
                        </rect>
                        {solar && (
                          <circle cx={r.x + r.w - 16} cy={r.y + 16} r={10} fill="#fbbf24" stroke="#000" strokeWidth={1.5}>
                            <title>태양광 시설 확인(YOLO)</title>
                          </circle>
                        )}
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          </div>

          {/* 우: 컨트롤 패널 */}
          <div className="w-72 border-l border-slate-700 p-4 overflow-y-auto text-xs text-slate-300">
            {/* 민감도 슬라이더 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-white">강도 필터</span>
                <span className="text-slate-400">{threshold.toFixed(1)}</span>
              </div>
              <p className="text-xs text-slate-400 mb-1 leading-snug">
                변화 판정은 VQ 코드북(할당 변화)이 이미 했습니다. 이 슬라이더는 그 중
                강도 낮은 것을 걸러 보는 보조 필터입니다.
              </p>
              <input
                type="range"
                min={minMag}
                max={maxMag}
                step={(maxMag - minMag) / 100 || 0.1}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-slate-400 mt-1">
                <span>민감 (후보 많음)</span>
                <span>둔감 (강한 변화만)</span>
              </div>
              <button
                type="button"
                onClick={() => setThreshold(serverThreshold)}
                className="mt-2 text-xs text-indigo-200 hover:text-indigo-100"
              >
                VQ 변화 전체 보기(강도 필터 해제)
              </button>
            </div>

            {/* 변화 그룹 */}
            <div className="mt-4 pt-3 border-t border-slate-700">
              <p className="font-bold text-white mb-1.5">변화 그룹</p>
              <p className="text-xs text-slate-400 leading-relaxed mb-2">
                <span className="text-slate-300">같은 코드워드 전이</span>(예: 코드워드 A→B)끼리
                묶은 익명 그룹입니다. 무엇의 변화인지(식생·시설물 등)는 시스템이 판정하지
                않습니다 — 배경을 전환해 직접 확인하고, 무관한 그룹은 꺼서 제외하세요.
              </p>
              {groupCounts.length === 0 && <p className="text-slate-400">변화 그룹 없음</p>}
              {groupCounts.map(([g, count]) => (
                <label key={g} className="flex items-center py-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!disabledGroups.has(g)}
                    onChange={() => toggleGroup(g)}
                    className="mr-2"
                  />
                  <span
                    className="inline-block w-3 h-3 rounded-sm mr-1.5"
                    style={{ backgroundColor: GROUP_COLORS[g % GROUP_COLORS.length] }}
                  />
                  <span className="text-slate-200">그룹 {GROUP_NAMES[g] ?? g}</span>
                  <span className="text-slate-400 ml-1">({count}개 패치)</span>
                </label>
              ))}
            </div>

            {/* 강도 상위 목록 */}
            <div className="mt-4 pt-3 border-t border-slate-700">
              <p className="font-bold text-white mb-1.5">변화 강도 상위</p>
              {topPatches.length === 0 && <p className="text-slate-400">현재 기준값에서 후보 없음</p>}
              {topPatches.map(({ i, m, g }, rank) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelectedPatch(selectedPatch === i ? null : i)}
                  className={`w-full flex items-center py-1 px-1.5 rounded text-left transition-colors ${
                    selectedPatch === i ? 'bg-slate-700' : 'hover:bg-slate-800'
                  }`}
                >
                  <span className="text-slate-400 inline-block w-5 text-right mr-2">{rank + 1}</span>
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5"
                    style={{ backgroundColor: GROUP_COLORS[g % GROUP_COLORS.length] }}
                  />
                  <span className="text-slate-200 flex-1">패치 #{i}</span>
                  <span className="text-slate-400">{m.toFixed(1)}</span>
                </button>
              ))}
            </div>

            {/* 정직성 캡션 */}
            <p className="mt-4 pt-3 border-t border-slate-700 text-xs text-slate-400 leading-relaxed">
              변화 판정은 <span className="text-slate-300">VQ 코드북</span>이 합니다 — 두 시점의
              특징을 같은 코드워드 어휘로 양자화해, 할당이 바뀐 패치를 변화로 봅니다. 무엇의
              변화인지(식생·시설물 등)와 후속 조치는 보는 사람의 몫입니다(비지도라 의미 라벨 없음).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
