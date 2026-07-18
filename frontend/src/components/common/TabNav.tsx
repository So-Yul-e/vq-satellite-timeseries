/**
 * TabNav — 05_design-common-system.md 계약
 * 4개 탭 고정, 페이지 이동이 아닌 콘텐츠 전환 — <button> 기반, role="tab"/aria-selected 적용.
 * md 미만에서 가로 스크롤 허용(탭 개수 고정이므로 줄바꿈 대신 스크롤).
 * icon: Phosphor Icons 컴포넌트(ReactNode)를 받는다 — 이모지 문자열 금지.
 */

import type { ReactNode } from 'react';

export interface TabNavItem {
  id: string;
  name: string;
  icon: ReactNode;
}

interface TabNavProps {
  tabs: TabNavItem[];
  activeTab: string;
  onChange: (id: string) => void;
}

export default function TabNav({ tabs, activeTab, onChange }: TabNavProps) {
  return (
    <div className="bg-slate-800 border-b border-slate-700 overflow-x-auto">
      <nav className="flex px-6 py-2" role="tablist">
        {tabs.map((tab, i) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
            className={`inline-flex items-center px-4 py-2 text-sm rounded-lg whitespace-nowrap transition-colors ${i === 0 ? '' : 'ml-1'} ${
              activeTab === tab.id
                ? // 활성 = 배경 반전(밝은 필 + accent 텍스트) — 어두운 UI에서 글자색만
                  // 바꾸는 것보다 대비·식별 모두 강함 (05 §접근성 배경 반전 규칙).
                  // 순백은 다크 UI에서 너무 튀어 85% 투명도로 톤 조절(사용자 피드백)
                  'bg-white/85 text-indigo-700 font-bold'
                : 'text-slate-300 hover:text-white hover:bg-slate-750'
            }`}
          >
            {/* 버튼 자체가 flex 컨테이너여야 아이콘과 텍스트가 세로 중앙 정렬됨
                (아이콘만 span으로 감싸면 텍스트 베이스라인에 걸터앉아 위로 뜸) */}
            <span className="mr-2">{tab.icon}</span>
            <span>{tab.name}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
