import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 환경에서 hot reload를 위한 설정
  output: "standalone",

  // 환경변수 타입 체크는 runtime에서 진행 (src/lib/env.ts 등에서)
  reactStrictMode: true,

  // Sprint 2+ 에서 이미지 원격 호스트 추가
  images: {
    remotePatterns: [],
  },

  experimental: {
    // Server Actions 최대 payload 크기 (파일 업로드 대비)
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
};

export default nextConfig;
