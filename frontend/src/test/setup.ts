import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// 각 테스트 후 렌더된 DOM 정리 (테스트 간 격리).
afterEach(() => {
  cleanup()
})

// antd 컴포넌트는 jsdom 에 없는 window.matchMedia 를 참조한다 → 폴리필.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

// antd 의 일부 컴포넌트(Segmented 등)가 ResizeObserver 를 요구할 수 있다 → 폴리필.
if (typeof window.ResizeObserver === 'undefined') {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
