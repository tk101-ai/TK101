export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return "";  // 새 데이터(Qdrant)는 size 없음 → 표기 생략
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(1)} KB`;
  }
  const mb = kb / 1024;
  if (mb < 1024) {
    return `${mb.toFixed(1)} MB`;
  }
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const date = formatDate(value);
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${date} ${hh}:${mi}`;
}

export function fileIconType(
  mimeType: string | null | undefined,
  fileType: string | null | undefined,
  name?: string | null,
): "pdf" | "doc" | "ppt" | "xls" | "hwp" | "image" | "file" {
  // 확장자 우선(Qdrant 결과는 mime_type 이 비어 있을 수 있음).
  const ext = (name ?? "").split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "pdf";
  if (ext === "doc" || ext === "docx") return "doc";
  if (ext === "ppt" || ext === "pptx") return "ppt";
  if (ext === "xls" || ext === "xlsx" || ext === "csv") return "xls";
  if (ext === "hwp" || ext === "hwpx") return "hwp";
  if (["png", "jpg", "jpeg", "gif", "webp", "bmp"].includes(ext)) return "image";
  // mime 폴백(null 안전).
  if (fileType === "image") return "image";
  const m = (mimeType ?? "").toLowerCase();
  if (m.includes("pdf")) return "pdf";
  if (m.includes("word") || m.includes("officedocument.wordprocessing")) return "doc";
  if (m.includes("powerpoint") || m.includes("presentation")) return "ppt";
  if (m.includes("excel") || m.includes("spreadsheet")) return "xls";
  if (m.includes("hwp") || m.includes("hancom")) return "hwp";
  return "file";
}
