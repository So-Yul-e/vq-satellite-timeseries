/**
 * VqTimelineScrubber — 연속(다시점) VQ 시계열 재생기 (2026-07-18)
 *
 * 2점 비교가 아니라 여러 연도를 훑는 진짜 시계열. 연도 슬라이더로 프레임(위성영상)을
 * 훑으면 기준(첫 연도) 대비 코드워드가 바뀐 패치가 누적돼 보인다. 아래 막대는 패치별
 * "처음 바뀐 연도" 분포 — 언제 변화가 일어났는지 한눈에.
 *
 * 변화 판정은 VQ 코드북(할당 변화)이 한다(2점 인스펙터와 동일 원리, N점으로 확장).
 */

'use client';

import { useMemo, useState } from 'react';
import type { VqTimeseriesResult } from '@/types/api';

interface VqTimelineScrubberProps {
  data: VqTimeseriesResult;
  imageBase: string; // API_BASE_URL — image_url 앞에 붙임
  contextLabel?: string;
  onClose: () => void;
}

export default function VqTimelineScrubber({ data, imageBase, contextLabel, onClose }: VqTimelineScrubberProps) {
  const { frames, patch_grid: grid, change_year: changeYear, years } = data;
  const [idx, setIdx] = useState(frames.length - 1); // 기본: 마지막 연도(누적 변화 최대)
  const frame = frames[idx];

  // 패치별 "처음 바뀐 연도" 분포 (막대용)
  const yearCounts = useMemo(() => {
    const m = new Map<number, number>();
    changeYear.forEach((y) => {
      if (y != null) m.set(y, (m.get(y) ?? 0) + 1);
    });
    return years.map((y) => ({ year: y, count: m.get(y) ?? 0 }));
  }, [changeYear, years]);
  const maxCount = Math.max(1, ...yearCounts.map((c) => c.count));

  const patchRect = (i: number) => {
    if (!grid) return { x: 0, y: 0, w: 0, h: 0 };
    const col = i % grid.n_x;
    const row = Math.floor(i / grid.n_x);
    const x = col * grid.stride;
    const y = row * grid.stride;
    return { x, y, w: Math.min(grid.patch_size, grid.image_width - x), h: Math.min(grid.patch_size, grid.image_height - y) };
  };

  const W = grid?.image_width ?? 1024;
  const H = grid?.image_height ?? 1024;

  return (
    <div className="fixed inset-0 z-[1000] bg-black/90 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-4xl max-h-[92vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <div>
            <p className="text-white font-bold text-sm">연속 시계열 — 타임라인</p>
            <p className="text-xs text-slate-400 mt-1">
              {contextLabel ?? '여러 연도 비교'} · {years[0]}~{years[years.length - 1]} · 기준 {years[0]}년 대비
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-300 hover:text-white text-sm px-2 py-1">
            닫기 ✕
          </button>
        </div>

        <div className="p-4 overflow-y-auto">
          {/* 프레임 + 변화 오버레이 */}
          <div className="relative bg-slate-950 rounded border border-slate-700 overflow-hidden" style={{ aspectRatio: `${W} / ${H}` }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${imageBase}${frame.image_url}`} alt={`${frame.year}년`} className="absolute inset-0 w-full h-full object-contain" />
            <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid meet">
              {frame.change_mask.map((changed, i) =>
                changed ? (
                  <rect key={i} {...(() => { const r = patchRect(i); return { x: r.x, y: r.y, width: r.w, height: r.h }; })()}
                    fill="#ef4444" fillOpacity={0.3} stroke="#ef4444" strokeWidth={2} />
                ) : null,
              )}
            </svg>
            <div className="absolute top-2 left-2 bg-slate-900/85 rounded px-2 py-1">
              <span className="text-white font-bold text-lg">{frame.year}년</span>
              <span className="text-xs text-slate-300 ml-2">기준 대비 변화 {frame.n_changed}곳</span>
              {frame.mean_cloud != null && <span className="text-xs text-slate-400 ml-2">구름 {frame.mean_cloud}%</span>}
            </div>
          </div>

          {/* 연도 슬라이더 */}
          <div className="mt-3">
            <input
              type="range"
              min={0}
              max={frames.length - 1}
              step={1}
              value={idx}
              onChange={(e) => setIdx(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between mt-1">
              {frames.map((f, i) => (
                <button
                  key={f.year}
                  type="button"
                  onClick={() => setIdx(i)}
                  className={`text-xs px-1.5 py-0.5 rounded ${i === idx ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                >
                  {f.year}
                </button>
              ))}
            </div>
          </div>

          {/* 변화 발생 연도 분포(막대) — 언제 변화가 일어났나 */}
          <div className="mt-4 pt-3 border-t border-slate-700">
            <p className="text-sm font-bold text-white mb-2">변화 발생 시점 (패치별 처음 바뀐 연도)</p>
            <div className="flex items-end" style={{ height: 80 }}>
              {yearCounts.map((c, i) => (
                <button
                  key={c.year}
                  type="button"
                  onClick={() => setIdx(i)}
                  className={`flex-1 flex flex-col items-center justify-end ${i === 0 ? '' : 'ml-1'}`}
                  title={`${c.year}년: ${c.count}곳`}
                >
                  <div
                    className={`w-full rounded-t ${i === idx ? 'bg-indigo-400' : 'bg-red-500/70'}`}
                    style={{ height: `${(c.count / maxCount) * 60}px`, minHeight: c.count > 0 ? 4 : 0 }}
                  />
                  <span className="text-xs text-slate-400 mt-1">{String(c.year).slice(2)}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-2 leading-snug">
              막대 = 그 해에 처음 변한 패치 수. 첫 연도({years[0]}) 대비 코드워드 할당이 바뀐 시점입니다.
              막대/연도를 클릭하면 그 해 프레임으로 이동합니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
