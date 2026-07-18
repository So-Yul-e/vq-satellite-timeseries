/**
 * PanelDetailPopup — 05_design-common-system.md 계약
 * 패널 상세 팝업(위치·면적·신뢰도·품질점수·허가상태·위험도)을 단일 컴포넌트로 추출,
 * "탐지 지도" 탭 내 모든 진입 경로(마커 클릭·무허가 목록 클릭)에서 공유(02 IA 26행, 2026-07-12 3탭 재편).
 *
 * md 이상: 우측 슬라이드 패널 / md 미만: 하단 시트로 전환(막다른 상태 금지 — 닫기 경로 항상 노출).
 */

import type { ReactNode } from 'react';
import {
  X,
  FileText,
  Warning,
  WarningCircle,
  Target,
  Mountains,
  Tree,
  Drop,
  ShieldWarning,
  CheckCircle,
  Prohibit,
} from '@phosphor-icons/react';
import type { DetectedPanel } from '@/types/api';
import StatusBadge, { StatusBadgeStatus } from './StatusBadge';

interface PanelDetailPopupProps {
  panel: DetectedPanel;
  onClose: () => void;
  loading?: boolean;
  error?: string | null;
  /** 위험도 섹션 전용 로딩/에러 — 기본 정보(위치·신뢰도·허가상태)는 즉시 표시하고
   *  위험도만 별도 비동기 조회이므로 전체 팝업 loading/error와 분리한다(FR-205). */
  riskLoading?: boolean;
  riskError?: string | null;
}

function riskBarColor(score: number): string {
  if (score >= 80) return 'bg-red-500';
  if (score >= 60) return 'bg-orange-500';
  if (score >= 40) return 'bg-yellow-500';
  return 'bg-green-500';
}

function riskLevelLabel(level: string): ReactNode {
  switch (level) {
    case 'critical':
      return (
        <span className="inline-flex items-center">
          <Prohibit size={14} className="mr-1" />매우 위험
        </span>
      );
    case 'high':
      return (
        <span className="inline-flex items-center">
          <WarningCircle size={14} weight="fill" className="mr-1 text-red-500" />높음
        </span>
      );
    case 'medium':
      return (
        <span className="inline-flex items-center">
          <WarningCircle size={14} weight="fill" className="mr-1 text-yellow-500" />보통
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center">
          <CheckCircle size={14} weight="fill" className="mr-1 text-green-500" />낮음
        </span>
      );
  }
}

export default function PanelDetailPopup({ panel, onClose, loading, error, riskLoading, riskError }: PanelDetailPopupProps) {
  const area = panel.area ?? panel.area_m2 ?? 0;

  return (
    <div
      className="fixed md:absolute top-0 right-0 bottom-0 w-full md:w-96 bg-slate-800 border-l border-slate-700 shadow-2xl z-[1000] overflow-y-auto"
      role="dialog"
      aria-label="패널 상세 정보"
    >
      <div className="p-5">
        <div className="flex justify-between items-start mb-4">
          <h4 className="font-bold text-white text-lg">패널 상세 정보</h4>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white leading-none"
            aria-label="닫기"
          >
            <X size={20} />
          </button>
        </div>

        {loading && (
          <div className="space-y-3 animate-pulse">
            <div className="h-4 bg-slate-700 rounded w-3/4" />
            <div className="h-4 bg-slate-700 rounded w-1/2" />
            <div className="h-20 bg-slate-700 rounded" />
          </div>
        )}

        {error && !loading && (
          <p className="text-sm text-red-400 bg-red-900/20 border border-red-500/30 rounded px-3 py-2">
            {error}
          </p>
        )}

        {!loading && !error && (
          <div className="space-y-4 text-sm">
            {/* 기본 정보 */}
            <div className="space-y-2">
              <div>
                <p className="text-slate-400 text-xs">ID</p>
                <p className="font-mono text-white text-xs break-all mt-0.5">{panel.id}</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs">위치</p>
                <p className="text-white mt-0.5">{panel.latitude.toFixed(6)}, {panel.longitude.toFixed(6)}</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs">면적</p>
                <p className="text-white mt-0.5">{area.toFixed(2)} m²</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs">탐지 신뢰도</p>
                <p className="text-white mt-0.5">{(panel.confidence * 100).toFixed(1)}%</p>
              </div>

              {panel.quality_score !== undefined && (
                <div>
                  <p className="text-slate-400 text-xs">품질 점수</p>
                  <div className="flex items-center mt-0.5">
                    <div className="flex-1 bg-slate-700 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${
                          panel.quality_score >= 70 ? 'bg-green-500' : panel.quality_score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${panel.quality_score}%` }}
                      />
                    </div>
                    <span className="text-white font-bold ml-2">{panel.quality_score.toFixed(0)}</span>
                  </div>
                </div>
              )}

              <div>
                <p className="text-slate-400 text-xs mb-1">허가 상태</p>
                <StatusBadge status={panel.permit_status as StatusBadgeStatus} />
              </div>
            </div>

            {/* 허가 상세 정보 */}
            {panel.permit_info && (
              <div className="border-t border-slate-700 pt-3">
                <h5 className="font-bold text-white mb-2 flex items-center">
                  <FileText size={16} className="mr-1.5" />허가 정보
                </h5>
                {panel.permit_info.has_permit ? (
                  <div className="space-y-2">
                    {panel.permit_info.applicant_name && (
                      <div className="bg-slate-750 bg-slate-700/40 p-2.5 rounded">
                        <p className="text-slate-400 text-xs mb-1">시설명/신청인</p>
                        <p className="text-white text-xs">{panel.permit_info.applicant_name}</p>
                      </div>
                    )}
                    {panel.permit_info.issuing_authority && (
                      <div className="bg-slate-700/40 p-2.5 rounded">
                        <p className="text-slate-400 text-xs mb-1">발급 기관</p>
                        <p className="text-white text-xs">{panel.permit_info.issuing_authority}</p>
                      </div>
                    )}
                    {panel.permit_info.permit_area_m2 !== undefined && (
                      <div className="bg-slate-700/40 p-2.5 rounded">
                        <p className="text-slate-400 text-xs mb-1">허가 용량</p>
                        <p className="text-white text-xs">{panel.permit_info.permit_area_m2} m²</p>
                      </div>
                    )}
                    {panel.permit_info.match_quality && (
                      <p className="text-xs text-slate-400">
                        매칭 품질:{' '}
                        <span className="text-white font-bold">{panel.permit_info.match_quality}</span>
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="bg-red-900/20 border border-red-700 p-3 rounded">
                    <p className="text-red-400 text-sm font-bold mb-1 flex items-center">
                      <Warning size={16} className="mr-1.5" />허가 미발견
                    </p>
                    <p className="text-red-300 text-xs">
                      {panel.permit_info.reason || '반경 100m 내에 등록된 허가 데이터가 없습니다'}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* 위험도 평가 — 전체 섹션은 항상 표시, 항목별 실패는 "측정 불가" (FR-205) */}
            {riskLoading && (
              <div className="border-t border-slate-700 pt-3">
                <h5 className="font-bold text-white mb-2 flex items-center">
                  <Target size={16} className="mr-1.5" />위험도 평가
                </h5>
                <div className="space-y-2 animate-pulse">
                  <div className="h-4 bg-slate-700 rounded w-1/2" />
                  <div className="h-12 bg-slate-700 rounded" />
                </div>
              </div>
            )}

            {!riskLoading && riskError && (
              <div className="border-t border-slate-700 pt-3">
                <h5 className="font-bold text-white mb-2 flex items-center">
                  <Target size={16} className="mr-1.5" />위험도 평가
                </h5>
                <p className="text-xs text-red-400 bg-red-900/20 border border-red-500/30 rounded px-2 py-1.5">
                  위험도 평가 조회 실패: {riskError}
                </p>
              </div>
            )}

            {!riskLoading && !riskError && panel.risk_assessment && (
              <div className="border-t border-slate-700 pt-3">
                <h5 className="font-bold text-white mb-2 flex items-center">
                  <Target size={16} className="mr-1.5" />위험도 평가
                  {/* 배지 자체가 flex여야 내부 아이콘+텍스트가 세로 중앙 정렬됨 —
                      일반 인라인 span이면 안쪽 inline-flex가 베이스라인에 걸터앉아
                      "낮음" 텍스트가 아래로 처져 보이던 문제(line-height 어긋남) */}
                  <span className="ml-2 px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-200 inline-flex items-center">
                    {riskLevelLabel(panel.risk_assessment.risk_level)}
                  </span>
                </h5>
                <p className="text-xs text-slate-400 bg-slate-900/40 border border-slate-700 rounded px-2 py-1.5 mb-2">
                  이 지표는 판정 근거가 아닌 보조 신호입니다.
                </p>

                <div className="space-y-2">
                  <div>
                    <p className="text-slate-400 text-xs">종합 위험 점수</p>
                    <div className="flex items-center mt-0.5">
                      <div className="flex-1 bg-slate-700 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${riskBarColor(panel.risk_assessment.total_risk_score)}`}
                          style={{ width: `${panel.risk_assessment.total_risk_score}%` }}
                        />
                      </div>
                      <span className="text-white font-bold ml-2">{panel.risk_assessment.total_risk_score}</span>
                    </div>
                  </div>

                  <RiskItem
                    icon={<Mountains size={14} />}
                    label="경사도"
                    value={panel.risk_assessment.slope_degree === null ? null : `${panel.risk_assessment.slope_degree.toFixed(1)}°`}
                    score={panel.risk_assessment.slope_risk_score}
                  />
                  <RiskItem
                    icon={<Tree size={14} />}
                    label="산림 훼손"
                    value={
                      panel.risk_assessment.forest_damage_area_m2 === null
                        ? null
                        : `${panel.risk_assessment.forest_damage_area_m2.toFixed(0)} m²`
                    }
                    score={panel.risk_assessment.forest_risk_score}
                  />
                  <RiskItem
                    icon={<Drop size={14} />}
                    label="수계 거리"
                    value={
                      panel.risk_assessment.water_distance_m === null
                        ? null
                        : `${panel.risk_assessment.water_distance_m.toFixed(0)} m`
                    }
                    score={panel.risk_assessment.water_risk_score}
                  />
                  <div className="bg-slate-700/40 p-2.5 rounded">
                    <p className="text-slate-400 text-xs mb-1 flex items-center">
                      <ShieldWarning size={14} className="mr-1" />보호 구역
                    </p>
                    <div className="flex justify-between items-center">
                      {panel.risk_assessment.protected_area_violation === null ? (
                        <span className="text-slate-400 text-xs">측정 불가</span>
                      ) : (
                        <span className={`font-bold inline-flex items-center ${panel.risk_assessment.protected_area_violation ? 'text-red-400' : 'text-green-400'}`}>
                          {panel.risk_assessment.protected_area_violation ? (
                            <><Warning size={14} className="mr-1" />침범</>
                          ) : (
                            <><CheckCircle size={14} weight="fill" className="mr-1" />정상</>
                          )}
                        </span>
                      )}
                      <span className="text-xs text-slate-400">위험도: {panel.risk_assessment.protected_risk_score ?? '—'}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!riskLoading && !riskError && !panel.risk_assessment && (
              <div className="border-t border-slate-700 pt-3">
                <p className="text-slate-400 text-xs text-center py-2">위험도 평가 정보가 없습니다</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RiskItem({ icon, label, value, score }: { icon: ReactNode; label: string; value: string | null; score: number | null }) {
  return (
    <div className="bg-slate-700/40 p-2.5 rounded">
      <p className="text-slate-400 text-xs mb-1 inline-flex items-center">
        <span className="inline-flex items-center mr-1">{icon}</span>{label}
      </p>
      <div className="flex justify-between items-center">
        <span className="text-white">{value ?? <span className="text-slate-400">측정 불가</span>}</span>
        <span className="text-xs text-slate-400">위험도: {score ?? '—'}</span>
      </div>
    </div>
  );
}
