import { describe, expect, it } from 'vitest'
import { fileIconType, formatDate, formatDateTime, formatFileSize } from './nasUtils'

describe('formatFileSize', () => {
  it('null/0 이하 값은 빈 문자열을 반환한다 (Qdrant 결과는 size 없음)', () => {
    expect(formatFileSize(null)).toBe('')
    expect(formatFileSize(undefined)).toBe('')
    expect(formatFileSize(0)).toBe('')
    expect(formatFileSize(-5)).toBe('')
  })

  it('1024 미만은 바이트 단위로 표기한다', () => {
    expect(formatFileSize(512)).toBe('512 B')
  })

  it('KB/MB/GB 단위로 변환한다', () => {
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(formatFileSize(2 * 1024 * 1024 * 1024)).toBe('2.00 GB')
  })
})

describe('formatDate', () => {
  it('빈 값은 대시를 반환한다', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate(undefined)).toBe('-')
    expect(formatDate('')).toBe('-')
  })

  it('ISO 날짜를 YYYY-MM-DD 로 변환한다', () => {
    expect(formatDate('2026-06-18T10:30:00')).toBe('2026-06-18')
  })

  it('파싱 불가한 값은 원본을 그대로 반환한다', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })
})

describe('formatDateTime', () => {
  it('빈 값은 대시를 반환한다', () => {
    expect(formatDateTime(null)).toBe('-')
  })

  it('날짜+시각(HH:mm) 형식으로 변환한다', () => {
    expect(formatDateTime('2026-06-18T09:05:00')).toBe('2026-06-18 09:05')
  })
})

describe('fileIconType', () => {
  it('확장자를 우선해 아이콘 타입을 결정한다', () => {
    expect(fileIconType(null, null, 'report.pdf')).toBe('pdf')
    expect(fileIconType(null, null, 'plan.docx')).toBe('doc')
    expect(fileIconType(null, null, 'deck.pptx')).toBe('ppt')
    expect(fileIconType(null, null, 'data.xlsx')).toBe('xls')
    expect(fileIconType(null, null, 'old.hwp')).toBe('hwp')
    expect(fileIconType(null, null, 'logo.png')).toBe('image')
  })

  it('확장자가 없으면 mime/fileType 으로 폴백한다', () => {
    expect(fileIconType('application/pdf', null, 'file')).toBe('pdf')
    expect(fileIconType(null, 'image', 'file')).toBe('image')
    expect(fileIconType(null, null, 'unknown')).toBe('file')
  })
})
