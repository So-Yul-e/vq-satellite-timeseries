/**
 * ButtonSpinner — 버튼 내부 인라인 로딩 스피너 (05 design-system 컴포넌트 계약)
 *
 * 용도: "실행 중..." 상태의 버튼 안에서 텍스트 왼쪽에 붙는 작은 스피너.
 * 블록 단위 로딩은 LoadingState를 쓰고, 이 컴포넌트는 버튼 인라인 전용이다.
 *
 * 사용 규칙:
 * - 버튼이 `flex items-center justify-center`일 때 텍스트 앞에 배치
 * - 간격은 자체 mr-2로 처리 — 호출부에서 별도 마진 불필요
 * - 표시 조건(어느 버튼이 실행 주체인지)은 호출부 책임
 *   (예: `{processing && runMode === 'location' && <ButtonSpinner />}`)
 */

export default function ButtonSpinner() {
  return (
    <span className="inline-block h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
  );
}
