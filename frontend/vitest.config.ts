import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 단위/스모크 테스트 설정. vite.config.ts 와 분리해 빌드 설정을 오염시키지 않는다.
// https://vitest.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
