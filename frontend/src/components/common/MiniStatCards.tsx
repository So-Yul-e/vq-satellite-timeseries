/**
 * MiniStatCards — 사이드패널용 소형 통계 카드 행 (05 design-system 컴포넌트 계약)
 *
 * 용도: "숫자 + 라벨"을 가로로 나란히 보여주는 요약 카드(2~3개).
 * AI 탐지 탭의 "이번 탐지 결과", 무허가 관리 탭의 "매칭 현황"이 공유한다.
 * 큰 대시보드 카드는 StatCard(트렌드·단위 포함)를 쓰고, 이건 패널 내 요약 전용.
 *
 * 계약:
 * - count가 null이면 "—"로 표시(로딩/결측과 0건을 구분 — 0은 0으로 보여준다)
 * - tone은 semantic 텍스트 색 클래스(예: 'text-red-400') — 05 판정 상태 토큰과 연동
 * - 간격은 margin 기반(ml-1.5), gap 금지(전역 제약)
 */

export interface MiniStat {
  label: string;
  count: number | null;
  tone: string; // 예: 'text-red-400' | 'text-green-400' | 'text-yellow-400'
}

export default function MiniStatCards({ items }: { items: MiniStat[] }) {
  return (
    <div className="flex text-center">
      {items.map((s, i) => (
        <div key={s.label} className={`flex-1 bg-slate-900 rounded py-2 ${i === 0 ? '' : 'ml-1.5'}`}>
          <p className={`text-lg font-bold ${s.tone}`}>{s.count ?? '—'}</p>
          <p className="text-xs text-slate-400 mt-0.5">{s.label}</p>
        </div>
      ))}
    </div>
  );
}
