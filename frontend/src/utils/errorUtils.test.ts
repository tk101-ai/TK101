import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'
import { extractErrorDetail } from './errorUtils'

function makeAxiosError(status: number, detail?: unknown): AxiosError {
  const err = new AxiosError('request failed')
  // axios 의 isAxiosError 판별을 위해 최소 형태를 갖춘 response 를 설정한다.
  err.response = {
    status,
    data: detail === undefined ? {} : { detail },
    statusText: '',
    headers: {},
    // @ts-expect-error 테스트용 최소 config
    config: {},
  }
  return err
}

describe('extractErrorDetail', () => {
  it('FastAPI 의 문자열 detail 을 우선 반환한다', () => {
    const err = makeAxiosError(400, '잘못된 요청입니다')
    expect(extractErrorDetail(err, '기본 메시지')).toBe('잘못된 요청입니다')
  })

  it('detail 이 없으면 statusMessages 매핑을 사용한다', () => {
    const err = makeAxiosError(403)
    expect(
      extractErrorDetail(err, '기본 메시지', {
        statusMessages: { 403: '관리자 권한 필요' },
      }),
    ).toBe('관리자 권한 필요')
  })

  it('매칭이 없으면 fallback 을 반환한다', () => {
    const err = makeAxiosError(500)
    expect(extractErrorDetail(err, '기본 메시지')).toBe('기본 메시지')
  })

  it('비-axios 에러는 fallback 을 반환한다', () => {
    expect(extractErrorDetail(new Error('boom'), '기본 메시지')).toBe('기본 메시지')
    expect(extractErrorDetail('문자열 에러', '기본 메시지')).toBe('기본 메시지')
  })

  it('useAxiosMessage 옵션이면 axios 메시지를 fallback 으로 쓴다', () => {
    const err = makeAxiosError(500)
    expect(
      extractErrorDetail(err, '기본 메시지', { useAxiosMessage: true }),
    ).toBe('request failed')
  })
})
