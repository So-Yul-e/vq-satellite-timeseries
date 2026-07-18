/**
 * API 응답 타입 정의
 * 08_api-contract.md 기준. useState<any> 금지 — 모든 API 응답은 이 타입들로 검증한다.
 */

// ---------- 공통 ----------

// 'pending' = 매칭 미확인(백엔드 /solar/analyze 실응답 값 — 구 타입에 누락돼
// 미확인 마커가 색 없이 렌더되던 문제의 원인, 2026-07-17 교정)
export type PermitStatus = 'legal' | 'illegal' | 'review' | 'pending';
export type MatchQuality = 'excellent' | 'good' | 'fair' | 'poor';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface ListResponse<T> {
  items: T[];
  total: number;
}

// ---------- 위험도 평가 (FR-205) ----------

export interface RiskAssessment {
  slope_degree: number | null;
  slope_risk_score: number | null;
  forest_damage_area_m2: number | null;
  forest_risk_score: number | null;
  water_distance_m: number | null;
  water_risk_score: number | null;
  protected_area_violation: boolean | null;
  protected_risk_score: number | null;
  total_risk_score: number;
  risk_level: RiskLevel;
}

// ---------- 허가 매칭 정보 (FR-202) ----------

export interface AreaMatch {
  matches: boolean;
  detected_area: number;
  permit_area: number;
  difference_m2?: number;
  difference_percent?: number;
  status?: string;
}

export interface PermitInfo {
  has_permit: boolean;
  is_legal: boolean;
  distance_m?: number;
  permit_id?: string;
  permit_number?: string;
  permit_type?: string;
  issuing_authority?: string;
  applicant_name?: string;
  permit_area_m2?: number;
  area_match?: AreaMatch;
  permit_start_date?: string;
  match_quality?: MatchQuality;
  reason?: string;
}

// ---------- 탐지된 패널 ----------

export interface DetectedPanel {
  id: string;
  detection_id?: string;
  latitude: number;
  longitude: number;
  area: number;
  area_m2?: number;
  confidence: number;
  permit_status: PermitStatus;
  quality_score?: number;
  quality_level?: 'high' | 'medium' | 'low';
  detection_method?: string;
  detection_date?: string;
  permit_info?: PermitInfo;
  risk_assessment?: RiskAssessment;
}

// ---------- FR-201: AI 탐지 실행 (/api/solar/analyze) ----------

export interface QualityStats {
  high: number;
  medium: number;
  low: number;
  average_score: number;
  average_confidence: number;
}

export interface DetectionResult {
  total_panels: number;
  legal: number;
  illegal: number;
  pending: number;
  panels: DetectedPanel[];
  quality_stats?: QualityStats;
}

export interface SatelliteImageInfo {
  image_id: string;
  cloud_cover?: number;
  thumbnail_url?: string;
}

export interface AnalyzeResponse {
  success: boolean;
  detection: DetectionResult;
  satellite_image: SatelliteImageInfo;
}

// ---------- FR-401: VQ 파이프라인 ----------

export interface VqPanel {
  id: string;
  latitude: number;
  longitude: number;
  area: number;
  confidence: number;
  status: string;
}

// 실제 백엔드 응답(backend/app/tasks/vq_tasks.py _run_full_pipeline) 기준.
// panels/changeMapUrl 필드는 백엔드에 존재하지 않음 — 변화탐지 통계(change_result)와
// 클러스터링 결과(cluster_result)만 반환된다(2026-07-12 실측 교정).
export interface VqChangeStatistics {
  n_total: number;
  n_changed: number;
  n_unchanged: number;
  change_percentage: number;
  threshold: number;
}

export interface VqChangeResult {
  status?: string;
  statistics: VqChangeStatistics;
  threshold: number;
  // 패치별 변화 여부(서버 otsu threshold 기준) — 순서는 patch_grid의 y→x 순회
  change_mask?: boolean[];
  // 패치별 변화 강도(연속값, CVA ||Δv||) — 인스펙터가 threshold를 클라이언트에서
  // 재실행 없이 조절하는 재료(FR-402 28-3)
  change_magnitudes?: number[];
  // 패치별 변화 그룹 id(미변화=-1) — 비슷한 변화끼리의 비지도 군집, 익명(의미 라벨 금지)
  patch_groups?: number[];
}

// 패치 격자 메타 — 클라이언트 오버레이 렌더용. 순회는 y→x(백엔드 feature_extractor와 동일)
export interface VqPatchGrid {
  image_width: number;
  image_height: number;
  n_x: number;
  n_y: number;
  patch_size: number;
  stride: number;
}

export interface VqClusterResult {
  status?: string;
  n_clusters: number;
  algorithm: string;
}

export interface VqVisualization {
  t1_image_url: string | null;
  t2_image_url: string | null;
  overlay_image_url: string | null;
}

// GEE 시계열 취득 메타 — median 합성에 쓰인 구간·영상수·평균 구름
export interface VqTimeMeta {
  window_start: string;
  window_end: string;
  image_count: number;
  mean_cloud: number | null;
}

// 위치 기반 시계열 변화탐지(analyze-location) 실행 시의 실제 취득 컨텍스트.
// "어디서 어느 두 시점을 비교했나"를 결과에 붙여 검증 가능하게 한다.
export interface VqLocationInfo {
  latitude: number;
  longitude: number;
  buffer_km: number;
  past_date: string;
  current_date: string;
  // T2를 T1과 같은 계절(같은 월·최근 연도)로 자동 정렬했는지 + 조도/흐림 정규화 여부
  season_aligned?: boolean;
  radiometric_normalized?: boolean;
  t1_meta: VqTimeMeta | null;
  t2_meta: VqTimeMeta | null;
  t1_tile_url: string | null;
  t2_tile_url: string | null;
  diff_tile_url: string | null;
  bounds?: number[][][];
  // YOLO 교차참조: AOI에서 탐지된 태양광 패널 수 + 그 중 VQ 변화와 겹친 패치 인덱스.
  // "이 변화 지점에 태양광 시설이 있다"는 정직한 도메인 라벨(고해상 VWorld+YOLO).
  solar_panel_count?: number;
  solar_changed_patches?: number[];
}

// 연속(다시점) VQ 시계열 — 연도별 프레임 + 변화 발생 연도
export interface VqTimeseriesFrame {
  year: number;
  image_url: string;
  change_mask: boolean[]; // 기준(첫 연도) 대비 코드워드가 바뀐 패치
  n_changed: number;
  mean_cloud: number | null;
}
export interface VqTimeseriesResult {
  years: number[];
  frames: VqTimeseriesFrame[];
  change_year: (number | null)[]; // 패치별 기준과 처음 달라진 연도
  patch_grid: VqPatchGrid | null;
  codebook_size: number;
}

export interface VqPipelineResult {
  status?: string;
  output_dir?: string;
  timeseries?: VqTimeseriesResult;
  change_result?: VqChangeResult;
  cluster_result?: VqClusterResult;
  // T1/T2 원본 + 변화 오버레이(빨간 박스) — 통계만으론 무엇이 비교됐는지 검증
  // 불가하던 문제 해소(2026-07-13). API_URL을 붙여서 <img src>로 사용.
  visualization?: VqVisualization;
  // 위치 기반 실행일 때만 존재 — 실제 위성 시계열 취득 컨텍스트.
  location?: VqLocationInfo;
  // 클라이언트 오버레이 렌더용 격자 메타(28-3 인스펙터)
  patch_grid?: VqPatchGrid | null;
}

export interface VqTaskStatus {
  task_id: string;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | string;
  progress?: number;
  result?: VqPipelineResult;
  error?: string;
}

// 저장된 VQ 분석 실행 요약 (/api/vq/runs) — 결과 영속화, "최근 분석" 목록
export interface VqAnalysisRunSummary {
  id: string;
  latitude: number;
  longitude: number;
  buffer_km: number;
  past_date: string | null;
  current_date: string | null;
  n_total: number | null;
  n_changed: number | null;
  change_percentage: number | null;
  solar_panel_count: number | null;
  n_solar_patches: number | null;
  created_at: string | null;
}

// /api/vq/runs/{id} — 저장된 결과 전체(폴링 결과와 동일 shape)
export interface VqRunDetail {
  status: string;
  result: VqPipelineResult;
}

export interface VqUploadResponse {
  file_path: string;
}

export interface VqPipelineStartResponse {
  task_id: string;
}

// ---------- FR-502: 허가 데이터 통계 (/api/solar-permits/stats) ----------

export interface TopInstitution {
  name: string;
  count: number;
  total_capacity: number;
}

export interface SolarPermitStats {
  total: number;
  with_coordinates: number;
  total_capacity_kw: number;
  avg_capacity_kw: number;
  top_institutions?: TopInstitution[];
  by_year?: Record<string, number>;
  // 데이터 기준 시각(마지막 수동 임포트, UTC ISO) — 자동 갱신되는 데이터가 아님
  data_as_of?: string | null;
  // 마지막 성공 동기화 시각(UTC ISO 'Z') — 자동 동기화 기능 추가 시 채워짐(백엔드 동시 작업)
  last_sync_at?: string | null;
  // 최근 동기화 상태('success'|'failed'|'running'|'partial')
  last_sync_status?: string | null;
}

export interface SolarPermit {
  id: string;
  permit_number?: string;
  facility_name?: string;
  road_address?: string;
  lot_address?: string;
  institution_name?: string;
  capacity?: number;
  latitude?: number;
  longitude?: number;
}

// ---------- FR-202: 매칭 통계 (/api/matching/stats) ----------

export interface MatchingStats {
  illegal_panels: number;
  legal_panels: number;
  exact_matches: number;
  nearby_matches: number;
}

export interface IllegalPanel {
  id: string;
  detection_id?: string;
  latitude: number;
  longitude: number;
  area_m2?: number;
  confidence: number;
  detection_date?: string;
  permit_info?: PermitInfo;
}

// ---------- 지도 마커 (05 MapView 계약) ----------

export type MarkerStatus = 'legal' | 'illegal' | 'review' | 'pending' | 'permit';

export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  status: MarkerStatus;
  label?: string;
  polygon?: number[][];
  panel?: DetectedPanel;
}
