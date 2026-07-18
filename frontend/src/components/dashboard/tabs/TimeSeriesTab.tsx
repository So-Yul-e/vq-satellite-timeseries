/**
 * 시계열 변화탐지 탭 — 프로젝트 본래 목적의 전용 탭 (02 IA 21행 2026-07-17 재편, FR-401/402)
 * 같은 좌표의 과거(T1)·현재(T2) 위성영상을 GEE에서 받아 VQ 클러스터링으로 변화를 탐지한다.
 * 구 탐지 지도 탭의 접이식 구석에 있던 것을 첫 탭으로 승격 — 지도(지점 클릭·footprint·
 * 변화 오버레이) + 분석 설정 + 결과/인스펙터가 한 여정. 업로드·샘플 실행은 보조 접이식.
 * mock 데이터 렌더링 금지 — 서버 응답만 렌더링(FR-501).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { CaretDown, CaretUp } from '@phosphor-icons/react';
import { apiClient, isApiSuccess, API_BASE_URL } from '@/utils/apiClient';
import type {
  ListResponse,
  VqAnalysisRunSummary,
  VqLocationInfo,
  VqPatchGrid,
  VqPipelineStartResponse,
  VqRunDetail,
  VqTaskStatus,
  VqTimeseriesResult,
  VqUploadResponse,
  VqVisualization,
} from '@/types/api';
import VqChangeInspector from '@/components/dashboard/VqChangeInspector';
import VqTimelineScrubber from '@/components/dashboard/VqTimelineScrubber';
import ErrorBanner from '@/components/common/ErrorBanner';
import ButtonSpinner from '@/components/common/ButtonSpinner';
import RegionPresetSelect from './RegionPresetSelect';
import { formatDateTime } from './shared';

const MapView = dynamic(() => import('@/components/common/MapView'), { ssr: false });

const POLL_INTERVAL_MS = 2000;
const MAX_CONSECUTIVE_FAILURES = 5;
const POLL_TIMEOUT_MS = 60000;
// 위치 기반 시계열은 GEE 다운로드 + ResNet50(1024px) 추론이라 수 분 걸림 — 별도 타임아웃
const LOCATION_POLL_TIMEOUT_MS = 600000;

export default function TimeSeriesTab() {
  const [center, setCenter] = useState({ lat: 34.83, lng: 126.4 });
  const [zoom, setZoom] = useState(11);

  const [vqUploading, setVqUploading] = useState(false);
  const [vqProcessing, setVqProcessing] = useState(false);
  const [vqStatus, setVqStatus] = useState<VqTaskStatus | null>(null);
  const [vqError, setVqError] = useState<string | null>(null);
  const [vqSummary, setVqSummary] = useState<{
    changePercentage: number;
    threshold: number;
    nClusters: number;
    nChanged: number;
    nTotal: number;
  } | null>(null);
  const [vqVisualization, setVqVisualization] = useState<VqVisualization | null>(null);
  const [vqUsedSample, setVqUsedSample] = useState(false);
  const [vqLocationInfo, setVqLocationInfo] = useState<VqLocationInfo | null>(null);
  const [vqPastDate, setVqPastDate] = useState('2019-05-01');
  // 분석 모드: 2시점 비교(pair) vs 연속 다시점 시계열(timeseries)
  const [analysisMode, setAnalysisMode] = useState<'pair' | 'timeseries'>('pair');
  const nowYear = new Date().getFullYear();
  const [tsStartYear, setTsStartYear] = useState(2019);
  const [tsEndYear, setTsEndYear] = useState(nowYear);
  const [tsMonth, setTsMonth] = useState(5);
  const [vqTimeseries, setVqTimeseries] = useState<VqTimeseriesResult | null>(null);
  const [showScrubber, setShowScrubber] = useState(false);
  // 어느 진입점이 실행 중인가 — 스피너·진행 바는 누른 버튼에만
  const [vqRunMode, setVqRunMode] = useState<'location' | 'upload' | 'sample' | null>(null);
  const [vqBufferKm, setVqBufferKm] = useState(2);
  // 지도 클릭으로 지정한 분석 지점 — 미지정 시 지도 중심
  const [vqAnchor, setVqAnchor] = useState<{ lat: number; lng: number } | null>(null);
  const [showChangeOverlay, setShowChangeOverlay] = useState(true);
  const [lightbox, setLightbox] = useState<{ url: string; label: string } | null>(null);
  const [vqInspectorData, setVqInspectorData] = useState<{
    changeMask: boolean[];
    magnitudes: number[];
    groups: number[];
    patchGrid: VqPatchGrid;
    threshold: number;
  } | null>(null);
  const [showInspector, setShowInspector] = useState(false);
  // 최근 분석(결과 영속화) — 새로고침 후에도 남고, 클릭 시 재실행 없이 즉시 재표시
  const [recentRuns, setRecentRuns] = useState<VqAnalysisRunSummary[]>([]);
  const [loadingRun, setLoadingRun] = useState(false);
  // 보조 진입점(직접 업로드·샘플) — 기본 접힘
  const [altExpanded, setAltExpanded] = useState(false);
  const [imageT1, setImageT1] = useState<File | null>(null);
  const [imageT2, setImageT2] = useState<File | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);
  const pollTimeoutRef = useRef<number>(POLL_TIMEOUT_MS);
  const pollFailureCountRef = useRef<number>(0);
  const vqResultRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (vqSummary && !vqProcessing) {
      vqResultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [vqSummary, vqProcessing]);

  // 결과가 나오면 변화 오버레이만 켠다 — 지도 카메라는 건드리지 않음(예고 없는 이동 금지)
  useEffect(() => {
    if (vqLocationInfo) setShowChangeOverlay(true);
  }, [vqLocationInfo]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  // 최근 분석 목록 조회(영속화) — 마운트 시 + 분석 완료 후
  const fetchRuns = useCallback(async () => {
    const res = await apiClient.get<ListResponse<VqAnalysisRunSummary>>('/api/vq/runs?limit=20');
    if (isApiSuccess(res)) setRecentRuns(res.data.items);
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // 실제 백엔드 응답(change_result.statistics, cluster_result)을 그대로 반영 — 하드코딩 금지(FR-401)
  const applyPipelineResult = useCallback((status: VqTaskStatus) => {
    // 연속 시계열 결과면 별도 경로(2점 상태는 비우고 타임라인 준비)
    if (status.result?.timeseries) {
      setVqTimeseries(status.result.timeseries);
      setVqSummary(null);
      setVqVisualization(null);
      setVqInspectorData(null);
      setVqLocationInfo(null);
      setShowScrubber(true);
      return;
    }
    setVqTimeseries(null);
    const stats = status.result?.change_result?.statistics;
    const cluster = status.result?.cluster_result;
    if (stats) {
      setVqSummary({
        changePercentage: stats.change_percentage,
        threshold: stats.threshold,
        nClusters: cluster?.n_clusters ?? 0,
        nChanged: stats.n_changed,
        nTotal: stats.n_total,
      });
    }
    setVqVisualization(status.result?.visualization ?? null);
    setVqLocationInfo(status.result?.location ?? null);

    const cr = status.result?.change_result;
    const grid = status.result?.patch_grid;
    if (cr?.change_mask && cr.change_magnitudes && cr.patch_groups && grid && stats) {
      setVqInspectorData({
        changeMask: cr.change_mask,
        magnitudes: cr.change_magnitudes,
        groups: cr.patch_groups,
        patchGrid: grid,
        threshold: stats.threshold,
      });
    } else {
      setVqInspectorData(null);
    }
  }, []);

  // 저장된 실행 클릭 → 재실행 없이 즉시 재표시(applyPipelineResult 재사용 + 지도 이동)
  const loadRun = useCallback(async (id: string) => {
    setLoadingRun(true);
    setVqError(null);
    const res = await apiClient.get<VqRunDetail>(`/api/vq/runs/${id}`);
    setLoadingRun(false);
    if (isApiSuccess(res)) {
      setVqUsedSample(false);
      setVqRunMode('location');
      applyPipelineResult({ task_id: id, status: 'SUCCESS', result: res.data.result });
      const loc = res.data.result?.location;
      if (loc) {
        setCenter({ lat: loc.latitude, lng: loc.longitude });
        setZoom(Math.round(14 - Math.log2(Math.max(loc.buffer_km, 0.5))));
      }
    } else {
      setVqError(res.error.message);
    }
  }, [applyPipelineResult]);

  const checkTaskStatus = useCallback(
    async (taskId: string) => {
      const result = await apiClient.get<VqTaskStatus>(`/api/vq/task/${taskId}`);

      if (!isApiSuccess(result)) {
        pollFailureCountRef.current += 1;
      } else {
        pollFailureCountRef.current = 0;
        setVqStatus(result.data);

        if (result.data.status === 'SUCCESS') {
          stopPolling();
          setVqProcessing(false);
          applyPipelineResult(result.data);
          fetchRuns(); // 방금 저장된 실행을 목록에 반영
          return;
        }
        if (result.data.status === 'FAILURE') {
          stopPolling();
          setVqProcessing(false);
          setVqError(result.data.error || 'VQ 파이프라인 처리에 실패했습니다.');
          return;
        }
      }

      const elapsed = Date.now() - pollStartRef.current;
      if (pollFailureCountRef.current >= MAX_CONSECUTIVE_FAILURES || elapsed >= pollTimeoutRef.current) {
        stopPolling();
        setVqProcessing(false);
        setVqError('처리 시간 초과 — 다시 시도해주세요.');
      }
    },
    [stopPolling, applyPipelineResult, fetchRuns],
  );

  const startPolling = useCallback(
    (taskId: string, timeoutMs: number = POLL_TIMEOUT_MS) => {
      stopPolling();
      pollStartRef.current = Date.now();
      pollTimeoutRef.current = timeoutMs;
      pollFailureCountRef.current = 0;
      pollTimerRef.current = setInterval(() => {
        checkTaskStatus(taskId);
      }, POLL_INTERVAL_MS);
    },
    [checkTaskStatus, stopPolling],
  );

  const resetRun = (mode: 'location' | 'upload' | 'sample') => {
    setVqError(null);
    setVqSummary(null);
    setVqVisualization(null);
    setVqLocationInfo(null);
    setVqInspectorData(null);
    setVqTimeseries(null);
    setShowInspector(false);
    setShowScrubber(false);
    setVqUsedSample(mode === 'sample');
    setVqRunMode(mode);
  };

  // 연속(다시점) 시계열 — 여러 연도 같은 계절
  const handleAnalyzeTimeseries = useCallback(async () => {
    resetRun('location');
    setVqTimeseries(null);
    setVqProcessing(true);
    const target = vqAnchor ?? center;
    const result = await apiClient.post<VqPipelineStartResponse>('/api/vq/analyze-timeseries', {
      latitude: target.lat,
      longitude: target.lng,
      buffer_km: vqBufferKm,
      start_year: tsStartYear,
      end_year: tsEndYear,
      month: tsMonth,
    });
    if (isApiSuccess(result)) {
      startPolling(result.data.task_id, LOCATION_POLL_TIMEOUT_MS);
    } else {
      setVqProcessing(false);
      setVqError(result.error.message);
    }
  }, [center, vqAnchor, vqBufferKm, tsStartYear, tsEndYear, tsMonth, startPolling]);

  // 위치 기반 시계열 변화탐지 — 지정 지점(vqAnchor) 우선, 없으면 지도 중심
  const handleAnalyzeLocation = useCallback(async () => {
    resetRun('location');
    setVqProcessing(true);

    const target = vqAnchor ?? center;
    const result = await apiClient.post<VqPipelineStartResponse>('/api/vq/analyze-location', {
      latitude: target.lat,
      longitude: target.lng,
      buffer_km: vqBufferKm,
      past_date: vqPastDate,
      codebook_size: 128,
      n_clusters: 8,
    });

    if (isApiSuccess(result)) {
      startPolling(result.data.task_id, LOCATION_POLL_TIMEOUT_MS);
    } else {
      setVqProcessing(false);
      setVqError(result.error.message);
    }
  }, [center, vqAnchor, vqBufferKm, vqPastDate, startPolling]);

  const uploadImage = async (file: File): Promise<string | null> => {
    const formData = new FormData();
    formData.append('file', file);
    const result = await apiClient.post<VqUploadResponse>('/api/vq/upload', formData);
    if (isApiSuccess(result)) return result.data.file_path;
    setVqError(result.error.message);
    return null;
  };

  const handleStartPipeline = async () => {
    if (!imageT1 || !imageT2) {
      setVqError('시점 1, 시점 2 영상을 모두 업로드해주세요.');
      return;
    }
    resetRun('upload');
    setVqUploading(true);
    const path1 = await uploadImage(imageT1);
    const path2 = await uploadImage(imageT2);
    setVqUploading(false);
    if (!path1 || !path2) return;

    setVqProcessing(true);
    const result = await apiClient.post<VqPipelineStartResponse>('/api/vq/full-pipeline', {
      image_t1_path: path1,
      image_t2_path: path2,
      codebook_size: 256,
      n_clusters: 8,
    });

    if (isApiSuccess(result)) {
      startPolling(result.data.task_id);
    } else {
      setVqProcessing(false);
      setVqError(result.error.message);
    }
  };

  const handleRunSample = async () => {
    resetRun('sample');
    setVqProcessing(true);

    const result = await apiClient.post<VqPipelineStartResponse>('/api/vq/full-pipeline', {
      use_sample: true,
      codebook_size: 256,
      n_clusters: 8,
    });

    if (isApiSuccess(result)) {
      startPolling(result.data.task_id);
    } else {
      setVqProcessing(false);
      setVqError(result.error.message);
    }
  };

  const handleViewChange = useCallback((lat: number, lng: number, z: number) => {
    setCenter({ lat, lng });
    setZoom(z);
  }, []);

  // 분석 예정 영역(분석 지점 ± 반경) — 백엔드 aoi.bounds()와 동일한 박스
  const fpCenter = vqAnchor ?? center;
  const aoiFootprint = ((): [number, number][] => {
    const latD = vqBufferKm / 111;
    const lngD = vqBufferKm / (111 * Math.cos((fpCenter.lat * Math.PI) / 180));
    return [
      [fpCenter.lat + latD, fpCenter.lng - lngD],
      [fpCenter.lat + latD, fpCenter.lng + lngD],
      [fpCenter.lat - latD, fpCenter.lng + lngD],
      [fpCenter.lat - latD, fpCenter.lng - lngD],
    ];
  })();
  const zoomForBuffer = (km: number) => Math.round(14 - Math.log2(Math.max(km, 0.5)));

  // 진행 상태 — 실행한 버튼 바로 아래에 렌더
  const vqProgress =
    vqStatus && vqProcessing ? (
      <div className="text-xs text-slate-400 mt-2">
        <div className="flex items-center justify-between mb-1">
          <span className="text-slate-300">
            {vqStatus.result?.status && vqStatus.result.status !== 'completed'
              ? vqStatus.result.status
              : '작업 대기 중...'}
          </span>
          <span>{vqStatus.progress ?? 0}%</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded overflow-hidden">
          <div
            className="h-full bg-indigo-400 transition-all duration-500"
            style={{ width: `${vqStatus.progress ?? 0}%` }}
          />
        </div>
      </div>
    ) : null;

  return (
    <div className="h-full flex">
      {/* 사이드패널 — 분석 설정 → 실행 → 결과 (한 여정) */}
      <div className="w-96 bg-slate-800 border-r border-slate-700 flex flex-col overflow-y-auto">
        <div className="p-4 space-y-3">
          {/* 지역 프리셋 — 공통 컴포넌트(RegionPresetSelect), 지도 상태는 이 탭이 소유 */}
          <RegionPresetSelect
            onSelect={(lat, lng, z) => {
              setCenter({ lat, lng });
              setZoom(z);
            }}
          />

          {/* 분석 설정 (폰트: 설명 text-sm, 각주급만 text-xs — 05 최소 크기 규칙) */}
          <div className="bg-indigo-950/40 border border-indigo-500/40 rounded p-3 space-y-3">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">분석 지점</span>
                {vqAnchor && (
                  <button
                    type="button"
                    onClick={() => setVqAnchor(null)}
                    disabled={vqUploading || vqProcessing}
                    className="text-xs text-slate-400 hover:text-white underline"
                  >
                    해제
                  </button>
                )}
              </div>
              <p className={`text-sm font-bold mt-1 ${vqAnchor ? 'text-fuchsia-300' : 'text-slate-200'}`}>
                {(vqAnchor ?? center).lat.toFixed(4)}, {(vqAnchor ?? center).lng.toFixed(4)}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {vqAnchor ? '지도 클릭으로 지정됨' : '지도 중심 기준 · 지도를 클릭하면 고정'}
              </p>
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">분석 반경</label>
              <div className="flex -mr-1">
                {[1, 2, 3, 5].map((km) => (
                  <button
                    key={km}
                    type="button"
                    onClick={() => setVqBufferKm(km)}
                    disabled={vqUploading || vqProcessing}
                    className={`flex-1 mr-1 text-sm py-1.5 rounded border transition-colors ${
                      vqBufferKm === km
                        ? 'bg-indigo-600 border-indigo-500 text-white font-bold'
                        : 'bg-slate-900 border-slate-600 text-slate-300 hover:border-slate-500'
                    }`}
                  >
                    {km}km
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400 mt-1">넓을수록 위성 해상도가 낮아집니다 · 지도의 자홍 점선 = 분석 영역</p>
            </div>

            {/* 분석 모드: 2시점 비교 vs 연속(다시점) 시계열 */}
            <div>
              <label className="block text-sm text-slate-400 mb-1">분석 방식</label>
              <div className="flex bg-slate-900 rounded p-0.5">
                {([['pair', '2시점 비교'], ['timeseries', '연속 시계열']] as const).map(([m, label], i) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setAnalysisMode(m)}
                    disabled={vqUploading || vqProcessing}
                    className={`flex-1 text-sm py-1.5 rounded transition-colors ${i === 0 ? '' : 'ml-0.5'} ${
                      analysisMode === m ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {analysisMode === 'pair' ? (
              <div>
                <label className="block text-sm text-slate-400 mb-1">비교할 과거 시점 (T1)</label>
                <input
                  type="date"
                  value={vqPastDate}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setVqPastDate(e.target.value)}
                  disabled={vqUploading || vqProcessing}
                  className="w-full text-sm bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-white"
                />
              </div>
            ) : (
              <div>
                <label className="block text-sm text-slate-400 mb-1">연도 범위 · 계절(월)</label>
                <div className="flex items-center -mr-1.5">
                  <input type="number" min={2016} max={nowYear} value={tsStartYear}
                    onChange={(e) => setTsStartYear(Number(e.target.value))} disabled={vqProcessing}
                    className="flex-1 mr-1.5 text-sm bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-white" />
                  <span className="text-slate-400 text-sm mr-1.5">~</span>
                  <input type="number" min={2016} max={nowYear} value={tsEndYear}
                    onChange={(e) => setTsEndYear(Number(e.target.value))} disabled={vqProcessing}
                    className="flex-1 mr-1.5 text-sm bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-white" />
                  <select value={tsMonth} onChange={(e) => setTsMonth(Number(e.target.value))} disabled={vqProcessing}
                    className="text-sm bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-white">
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m}월</option>)}
                  </select>
                </div>
                <p className="text-xs text-slate-400 mt-1">연도별 같은 계절을 훑습니다(최대 10년). 오래 걸리지만 결과는 저장돼 재사용됩니다.</p>
              </div>
            )}

            <button
              type="button"
              onClick={analysisMode === 'pair' ? handleAnalyzeLocation : handleAnalyzeTimeseries}
              disabled={vqUploading || vqProcessing}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 text-white font-bold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center"
            >
              {vqProcessing && vqRunMode === 'location' && <ButtonSpinner />}
              {vqProcessing && vqRunMode === 'location'
                ? '분석 중... (수 분 소요)'
                : analysisMode === 'pair' ? '이 위치 시계열 분석' : '연속 시계열 분석'}
            </button>
            {vqRunMode === 'location' && vqProgress}

            {/* 연속 시계열 결과 → 타임라인 열기 */}
            {vqTimeseries && !vqProcessing && (
              <button
                type="button"
                onClick={() => setShowScrubber(true)}
                className="w-full bg-slate-700 hover:bg-slate-600 text-white font-bold py-2 rounded text-sm transition-colors"
              >
                타임라인 보기 ({vqTimeseries.years[0]}~{vqTimeseries.years[vqTimeseries.years.length - 1]}, {vqTimeseries.frames.length}개 연도)
              </button>
            )}
          </div>

          {/* 최근 분석(결과 영속화) — 클릭 시 재실행 없이 즉시 재표시 */}
          {recentRuns.length > 0 && (
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase mb-1">
                최근 분석
                {loadingRun && <span className="ml-2 text-slate-400 normal-case font-normal">불러오는 중...</span>}
              </label>
              <div className="space-y-1.5">
                {recentRuns.slice(0, 8).map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => loadRun(run.id)}
                    disabled={vqProcessing || loadingRun}
                    className="w-full text-left bg-slate-900 border border-slate-700 hover:border-indigo-500 rounded px-2.5 py-2 transition-colors disabled:opacity-50"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-200">
                        {run.latitude.toFixed(3)}, {run.longitude.toFixed(3)}
                      </span>
                      <span className="text-xs text-slate-400">{run.buffer_km}km</span>
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-xs text-slate-400">
                        {run.past_date} → {run.current_date} · 변화 {run.n_changed}/{run.n_total}
                      </span>
                      {(run.n_solar_patches ?? 0) > 0 && (
                        <span className="text-xs text-amber-300">☀{run.n_solar_patches}</span>
                      )}
                    </div>
                    {run.created_at && (
                      <p className="text-xs text-slate-400 mt-0.5">{formatDateTime(run.created_at)}</p>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 보조 진입점 — 직접 업로드 · 내장 샘플 (기본 접힘) */}
          <div className="border border-slate-700 rounded">
            <button
              type="button"
              onClick={() => setAltExpanded((v) => !v)}
              className="w-full flex items-center justify-between px-3 py-2.5 text-sm text-slate-300 hover:text-white transition-colors"
              aria-expanded={altExpanded}
            >
              <span>직접 이미지 업로드 · 샘플 실행</span>
              {altExpanded ? <CaretUp size={16} /> : <CaretDown size={16} />}
            </button>
            {altExpanded && (
              <div className="px-3 pb-3 space-y-3">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">시점 1 (과거)</label>
                  <input
                    type="file"
                    accept=".tif,.tiff,.jp2,.png,.jpg,.jpeg"
                    onChange={(e) => setImageT1(e.target.files?.[0] ?? null)}
                    disabled={vqUploading || vqProcessing}
                    className="w-full text-xs text-slate-300"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">시점 2 (최근)</label>
                  <input
                    type="file"
                    accept=".tif,.tiff,.jp2,.png,.jpg,.jpeg"
                    onChange={(e) => setImageT2(e.target.files?.[0] ?? null)}
                    disabled={vqUploading || vqProcessing}
                    className="w-full text-xs text-slate-300"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleStartPipeline}
                  disabled={vqUploading || vqProcessing || !imageT1 || !imageT2}
                  className="w-full bg-purple-600 hover:bg-purple-500 disabled:bg-slate-600 text-white font-bold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center"
                >
                  {(vqUploading || vqProcessing) && vqRunMode === 'upload' && (
                    <ButtonSpinner />
                  )}
                  {vqRunMode === 'upload' && vqUploading
                    ? '업로드 중...'
                    : vqRunMode === 'upload' && vqProcessing
                      ? '변화 탐지 중...'
                      : 'VQ 파이프라인 실행'}
                </button>
                {vqRunMode === 'upload' && vqProgress}

                <button
                  type="button"
                  onClick={handleRunSample}
                  disabled={vqUploading || vqProcessing}
                  className="w-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-600 text-white font-bold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center"
                >
                  {vqProcessing && vqRunMode === 'sample' && (
                    <ButtonSpinner />
                  )}
                  {vqProcessing && vqRunMode === 'sample' ? '샘플 처리 중...' : '내장 샘플로 실행'}
                </button>
                {vqRunMode === 'sample' && vqProgress}
              </div>
            )}
          </div>

          {vqError && (
            <ErrorBanner
              message={vqError}
              onRetry={() => {
                setVqError(null);
                if (vqRunMode === 'location') handleAnalyzeLocation();
                else if (vqRunMode === 'upload') handleStartPipeline();
                else if (vqRunMode === 'sample') handleRunSample();
              }}
              variant="inline"
            />
          )}

          {vqSummary && !vqProcessing && !vqError && (
            <div ref={vqResultRef} className="bg-slate-900/60 border border-indigo-500/60 rounded p-3 text-xs text-slate-300 space-y-1.5">
              <p className="font-bold text-white text-sm mb-1.5">변화탐지 결과</p>
              <div className="flex justify-between">
                <span className="text-slate-400">변화율</span>
                <span className="text-white font-bold">{vqSummary.changePercentage.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">변화 영역 / 전체</span>
                <span className="text-white">{vqSummary.nChanged} / {vqSummary.nTotal}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">threshold</span>
                <span className="text-white">{vqSummary.threshold.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">클러스터 수</span>
                <span className="text-white">{vqSummary.nClusters}</span>
              </div>

              {vqInspectorData && vqVisualization?.t2_image_url && (
                <button
                  type="button"
                  onClick={() => setShowInspector(true)}
                  className="w-full mt-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2 rounded text-xs transition-colors"
                >
                  변화 후보 살펴보기 (민감도·그룹별)
                </button>
              )}

              {vqVisualization?.overlay_image_url && (
                <div className="pt-3 border-t border-slate-700 space-y-2">
                  {vqLocationInfo ? (
                    <div className="space-y-2">
                      <p className="text-slate-300 leading-relaxed">
                        <span className="text-indigo-200 font-bold">실제 위성영상</span>{' '}
                        (Sentinel-2). 좌표{' '}
                        <span className="text-white">
                          {vqLocationInfo.latitude.toFixed(4)}, {vqLocationInfo.longitude.toFixed(4)}
                        </span>
                        의 두 시점을 VQ로 비교한 결과입니다.
                      </p>
                      <div className="bg-slate-800/60 rounded p-2.5 space-y-1 text-slate-400">
                        <div className="flex justify-between">
                          <span>시점1 (과거)</span>
                          <span className="text-slate-200">
                            {vqLocationInfo.t1_meta?.window_start}~{vqLocationInfo.t1_meta?.window_end}
                            {vqLocationInfo.t1_meta?.mean_cloud != null && ` · 구름 ${vqLocationInfo.t1_meta.mean_cloud}%`}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span>시점2 {vqLocationInfo.season_aligned ? '(같은 계절 최근)' : '(현재)'}</span>
                          <span className="text-slate-200">
                            {vqLocationInfo.t2_meta?.window_start}~{vqLocationInfo.t2_meta?.window_end}
                            {vqLocationInfo.t2_meta?.mean_cloud != null && ` · 구름 ${vqLocationInfo.t2_meta.mean_cloud}%`}
                          </span>
                        </div>
                      </div>
                      {(vqLocationInfo.season_aligned || vqLocationInfo.radiometric_normalized) && (
                        <p className="text-xs text-slate-400 leading-relaxed">
                          {vqLocationInfo.season_aligned && `T2를 T1과 같은 계절(${vqLocationInfo.current_date})로 자동 정렬`}
                          {vqLocationInfo.season_aligned && vqLocationInfo.radiometric_normalized && ' + '}
                          {vqLocationInfo.radiometric_normalized && '조도·흐림 정규화'}
                          {' '}— 계절/날씨 노이즈를 줄였습니다.
                        </p>
                      )}
                      {(vqLocationInfo.solar_changed_patches?.length ?? 0) > 0 && (
                        <p className="text-xs text-amber-300 leading-relaxed">
                          ☀ 변화 지점 중 <span className="font-bold">{vqLocationInfo.solar_changed_patches!.length}곳</span>에서
                          태양광 시설 확인(고해상 VWorld+YOLO 교차참조){vqLocationInfo.solar_panel_count != null && ` · 패널 ${vqLocationInfo.solar_panel_count}개 탐지`}.
                          인스펙터에서 노란 테두리로 표시됩니다.
                        </p>
                      )}
                      <p className="text-xs text-amber-400/80 leading-relaxed">
                        ※ 정규화 후에도 비지도라 잔여 식생 변화가 일부 남을 수 있습니다.
                      </p>
                    </div>
                  ) : vqUsedSample ? (
                    <p className="text-slate-400 leading-relaxed">
                      <span className="text-amber-400 font-bold">테스트용 합성 이미지</span>
                      입니다(실제 위성/항공사진 아님, 좌표 없음). VQ 알고리즘 자체가
                      정상 동작함을 보여주는 데모입니다.
                    </p>
                  ) : (
                    <p className="text-slate-400 leading-relaxed">
                      업로드하신 두 이미지를 224px 단위 패치로 나눠 비교한 결과입니다.
                      지도 좌표와는 연결되지 않습니다.
                    </p>
                  )}
                  <p className="text-slate-400">
                    시점1(과거) · 시점2(최근) · 변화 영역(
                    <span className="text-red-400">빨간 박스</span>) · 이미지 클릭 시 확대
                    {vqLocationInfo && <span className="text-indigo-200">, 지도에도 오버레이 표시됨</span>}
                  </p>
                  <div className="grid grid-cols-3">
                    {[
                      { url: vqVisualization.t1_image_url, label: '시점1' },
                      { url: vqVisualization.t2_image_url, label: '시점2' },
                      { url: vqVisualization.overlay_image_url, label: '변화 영역' },
                    ].map((img, i) => (
                      <div key={img.label} className={i === 0 ? '' : 'ml-1'}>
                        {img.url ? (
                          <button
                            type="button"
                            onClick={() => setLightbox({ url: img.url!, label: img.label })}
                            className="block w-full rounded border border-slate-600 overflow-hidden cursor-zoom-in hover:border-indigo-400 transition-colors"
                            title="클릭해서 크게 보기"
                          >
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={`${API_BASE_URL}${img.url}`}
                              alt={img.label}
                              className="w-full aspect-square object-cover"
                            />
                          </button>
                        ) : (
                          <div className="w-full aspect-square rounded border border-slate-700 bg-slate-800 flex items-center justify-center text-slate-400">
                            없음
                          </div>
                        )}
                        <p className="text-center text-slate-400 mt-1">{img.label}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 지도 — 지점 클릭 지정 + footprint + 변화 타일 오버레이 */}
      <div className="flex-1 relative">
        <MapView
          markers={[]}
          center={center}
          zoom={zoom}
          aoiFootprint={aoiFootprint}
          anchorPoint={vqAnchor}
          onMapClick={!vqProcessing ? (lat, lng) => setVqAnchor({ lat, lng }) : undefined}
          tileOverlays={
            showChangeOverlay && vqLocationInfo
              ? [
                  ...(vqLocationInfo.t2_tile_url ? [{ url: vqLocationInfo.t2_tile_url, opacity: 1 }] : []),
                  ...(vqLocationInfo.diff_tile_url ? [{ url: vqLocationInfo.diff_tile_url, opacity: 0.75 }] : []),
                ]
              : undefined
          }
          onViewChange={handleViewChange}
        />

        {vqLocationInfo && (
          <div className="absolute top-4 right-4 z-[500] bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2.5 text-xs text-slate-300 shadow-lg max-w-[230px]">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={showChangeOverlay}
                onChange={(e) => setShowChangeOverlay(e.target.checked)}
                className="mr-2"
              />
              <span className="font-bold text-white text-sm">변화 영역 오버레이</span>
            </label>
            <p className="mt-1.5 flex items-center">
              <span className="inline-block w-3 h-3 rounded-sm bg-red-500/75 border border-red-400 mr-1.5" />
              NDVI 감소(식생→시설물 등) 영역
            </p>
            <p className="mt-1 text-slate-400 leading-snug">
              과거 {vqLocationInfo.past_date} → 현재 비교 · 배경은 현재(T2)
            </p>
            <button
              type="button"
              onClick={() => {
                setCenter({ lat: vqLocationInfo.latitude, lng: vqLocationInfo.longitude });
                setZoom(zoomForBuffer(vqLocationInfo.buffer_km));
              }}
              className="mt-2 w-full text-xs bg-slate-700 hover:bg-slate-600 text-white rounded py-1.5 transition-colors"
            >
              결과 영역으로 이동
            </button>
          </div>
        )}
      </div>

      {/* 변화 후보 인스펙터 */}
      {showScrubber && vqTimeseries && (
        <VqTimelineScrubber
          data={vqTimeseries}
          imageBase={API_BASE_URL}
          contextLabel={`${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}`}
          onClose={() => setShowScrubber(false)}
        />
      )}

      {showInspector && vqInspectorData && vqVisualization?.t1_image_url && vqVisualization?.t2_image_url && (
        <VqChangeInspector
          t1Url={`${API_BASE_URL}${vqVisualization.t1_image_url}`}
          t2Url={`${API_BASE_URL}${vqVisualization.t2_image_url}`}
          patchGrid={vqInspectorData.patchGrid}
          changeMask={vqInspectorData.changeMask}
          magnitudes={vqInspectorData.magnitudes}
          groups={vqInspectorData.groups}
          serverThreshold={vqInspectorData.threshold}
          solarPatches={vqLocationInfo?.solar_changed_patches ?? []}
          contextLabel={
            vqLocationInfo
              ? `${vqLocationInfo.latitude.toFixed(4)}, ${vqLocationInfo.longitude.toFixed(4)} · ${vqLocationInfo.past_date} → 현재 (Sentinel-2)`
              : vqUsedSample
                ? '테스트용 합성 샘플 (좌표 없음)'
                : '업로드 이미지 비교 (좌표 없음)'
          }
          onClose={() => setShowInspector(false)}
        />
      )}

      {/* 비교 이미지 확대 라이트박스 */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[1000] bg-black/85 flex items-center justify-center p-6"
          onClick={() => setLightbox(null)}
        >
          <div className="max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-white font-bold text-sm">{lightbox.label}</p>
              <button
                type="button"
                onClick={() => setLightbox(null)}
                className="text-slate-300 hover:text-white text-sm"
              >
                닫기 ✕
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE_URL}${lightbox.url}`}
              alt={lightbox.label}
              className="w-full rounded-lg border border-slate-600 max-h-[80vh] object-contain bg-slate-900"
            />
          </div>
        </div>
      )}
    </div>
  );
}
