import api from "./client";
import { triggerBlobDownload } from "../utils/download";

export interface DongaReportStatus {
  sheet_id: string;
  api_key_set: boolean;
  template_exists: boolean;
  template_path: string;
}

/** 설정 준비 상태(라이브 시트 키·양식 파일) 조회. */
export async function getDongaReportStatus(): Promise<DongaReportStatus> {
  const res = await api.get<DongaReportStatus>("/api/donga-report/status");
  return res.data;
}

export interface GenerateDongaReportParams {
  month: number;
  year?: number;
  basisDate?: string;
  includeNarrative?: boolean;
}

/** 지정 월의 운영보고서 .pptx 를 생성해 브라우저 다운로드. 라이브 구글시트에서 자료를 읽는다. */
export async function generateDongaReport({
  month,
  year = 2026,
  basisDate,
  includeNarrative = true,
}: GenerateDongaReportParams): Promise<{ china: number; na: number }> {
  const res = await api.post(
    "/api/donga-report/generate",
    null,
    {
      params: {
        month,
        year,
        basis_date: basisDate,
        include_narrative: includeNarrative,
      },
      responseType: "blob",
    },
  );
  const blob = new Blob([res.data], {
    type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  });
  triggerBlobDownload(blob, `동아제약_운영보고서_${year}년${month}월_초안.pptx`);
  // 생성 건수는 헤더로 전달(있으면).
  const meta = res.headers["x-report-meta"] as string | undefined;
  const m = meta?.match(/china=(\d+),na=(\d+)/);
  return { china: m ? Number(m[1]) : 0, na: m ? Number(m[2]) : 0 };
}
