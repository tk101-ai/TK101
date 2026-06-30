import { useEffect, useState } from "react";
import {
  Alert,
  Checkbox,
  DatePicker,
  Modal,
  Select,
  Space,
  Typography,
  message,
} from "antd";
import type { Dayjs } from "dayjs";
import {
  generateDongaReport,
  getDongaReportStatus,
  type DongaReportStatus,
} from "../../api/dongaReport";

const { Text, Paragraph } = Typography;

interface DongaReportModalProps {
  open: boolean;
  onClose: () => void;
}

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

/** 동아제약 운영보고서 생성 모달 — 월 선택 → 라이브 시트로 양식 자동 채움 → .pptx 다운로드. */
export default function DongaReportModal({ open, onClose }: DongaReportModalProps) {
  const now = new Date();
  const [month, setMonth] = useState<number>(now.getMonth() + 1);
  const [year, setYear] = useState<number>(now.getFullYear());
  const [basisDate, setBasisDate] = useState<Dayjs | null>(null);
  const [includeNarrative, setIncludeNarrative] = useState(true);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<DongaReportStatus | null>(null);

  useEffect(() => {
    if (!open) return;
    getDongaReportStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [open]);

  const notReady =
    status != null && (!status.api_key_set || !status.template_exists);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const basis = basisDate
        ? `${basisDate.year()}년 ${basisDate.month() + 1}월 ${basisDate.date()}일`
        : undefined;
      const { china, na } = await generateDongaReport({
        month,
        year,
        basisDate: basis,
        includeNarrative,
      });
      message.success(
        `운영보고서 초안 생성 완료 — 중화권 ${china}건, 북미 ${na}건. 다운로드를 확인하세요.`,
      );
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "생성 실패";
      message.error(`운영보고서 생성 실패: ${detail}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title="운영보고서 자동 작성"
      okText="보고서 생성 (.pptx)"
      onOk={handleGenerate}
      confirmLoading={loading}
      okButtonProps={{ disabled: notReady }}
      width={520}
    >
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        <Paragraph type="secondary" style={{ margin: 0 }}>
          구글시트(관리문서)의 해당 월 배포 데이터를 읽어 기존 운영보고서 양식의 표·요약을
          자동으로 채웁니다. 홍보 방향·진행 이슈는 AI 초안으로 채워지며 <Text strong>검수가
          필요</Text>합니다. 콘텐츠 Top3·댓글 분석 슬라이드는 수동으로 보완하세요.
        </Paragraph>

        {notReady && (
          <Alert
            type="warning"
            showIcon
            message="설정 미완료"
            description={
              <>
                {!status?.api_key_set && <div>· 구글시트 API 키 미설정</div>}
                {!status?.template_exists && (
                  <div>· 양식 파일 없음: {status?.template_path}</div>
                )}
              </>
            }
          />
        )}

        <Space size={10} wrap>
          <span>
            <Text type="secondary">연도</Text>{" "}
            <Select
              value={year}
              onChange={setYear}
              style={{ width: 100 }}
              options={[2025, 2026, 2027].map((y) => ({ value: y, label: `${y}년` }))}
            />
          </span>
          <span>
            <Text type="secondary">보고 월</Text>{" "}
            <Select
              value={month}
              onChange={setMonth}
              style={{ width: 90 }}
              options={MONTHS.map((m) => ({ value: m, label: `${m}월` }))}
            />
          </span>
        </Space>

        <span>
          <Text type="secondary">데이터 기준일(선택)</Text>{" "}
          <DatePicker
            value={basisDate}
            onChange={setBasisDate}
            placeholder="미지정 시 양식 기본값"
          />
        </span>

        <Checkbox
          checked={includeNarrative}
          onChange={(e) => setIncludeNarrative(e.target.checked)}
        >
          홍보 방향·진행 이슈 AI 초안 포함
        </Checkbox>
      </Space>
    </Modal>
  );
}
