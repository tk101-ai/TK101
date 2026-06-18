import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// API 모듈을 목킹해 실제 네트워크 호출을 차단한다(스모크 테스트 격리).
vi.mock('../../api/docgen', () => ({
  generateDocument: vi.fn(),
  downloadGeneratedDocx: vi.fn(),
}))

import DocGenPage from './DocGenPage'

describe('DocGenPage 렌더 스모크', () => {
  it('크래시 없이 마운트되고 핵심 UI 가 보인다', () => {
    render(<DocGenPage />)

    // 헤딩과 주요 액션 버튼이 렌더되는지 확인.
    expect(screen.getByRole('heading', { name: /문서 생성/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /초안 생성/ })).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText(/제안서를 작성해줘/),
    ).toBeInTheDocument()
  })

  it('입력 전에는 초안 생성 버튼이 비활성화되어 있다', () => {
    render(<DocGenPage />)
    expect(screen.getByRole('button', { name: /초안 생성/ })).toBeDisabled()
  })
})
