import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  InboxOutlined,
  ReloadOutlined,
  RiseOutlined,
} from "@ant-design/icons";
import type { UploadProps } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  COMPANY_FILTER_OPTIONS,
  COMPANY_SELECT_OPTIONS,
  type CustomsDeclarationOut,
  type CustomsSummaryOut,
  type CustomsUploadResult,
  type DistributionCompany,
  getCustomsSummary,
  listCustoms,
  uploadCustoms,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

/**
 * 면장(통관신고) 데이터 수집 페이지 (Priority 4).
 *
 * 핵심 비즈니스 규칙:
 * - 면장 신고가는 관세 절감 목적으로 실가의 75% 로 신고된다.
 * - 실가 = 신고가 ÷ 0.75 (백엔드가 적재 시 역산해 저장).
 *
 * 구성:
 * 1. 헤더 + 75% 역산 관계 안내 배너
 * 2. 엑셀 업로드 카드 (회사 선택 + Dragger + 결과/미리보기)
 * 3. 집계 카드 — 총 신고가 vs 총 실가(역산) + 회수된 차액
 * 4. 면장 목록 Table (회사/검색 필터, 페이지네이션)
 *
 * 백엔드: /api/distribution/customs/*
 */

const NUMBER_FORMATTER = new Intl.NumberFormat("ko-KR");

/** Decimal 문자열(또는 number) → 한국어 천단위 표기. null 은 em-dash. */
function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(num)) return "—";
  return NUMBER_FORMATTER.format(Math.round(num));
}

function toNumber(value: string | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export default function CustomsPage() {
  // 업로드 상태
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<CustomsUploadResult | null>(
    null,
  );
  const [uploadCompany, setUploadCompany] =
    useState<DistributionCompany>("래더엑스");

  // 조회 상태
  const [companyFilter, setCompanyFilter] = useState<
    DistributionCompany | "all"
  >("all");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<CustomsDeclarationOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [summary, setSummary] = useState<CustomsSummaryOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const companyParam = companyFilter === "all" ? undefined : companyFilter;

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [list, sum] = await Promise.all([
        listCustoms({
          company_label: companyParam,
          search: search.trim() || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        }),
        getCustomsSummary(companyParam),
      ]);
      setRows(list.items);
      setTotal(list.total);
      setSummary(sum);
    } catch (err: unknown) {
      const detail = extractErrorDetail(err, "면장 데이터 조회 실패", {
        useAxiosMessage: true,
      });
      setErrorMsg(detail);
    } finally {
      setLoading(false);
    }
  }, [companyParam, search, page, pageSize]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const ratio = summary?.declare_ratio ?? 0.75;
  const ratioPercent = Math.round(ratio * 100);

  // 회수된 차액 = 실가 - 신고가 (역산으로 드러난 숨은 가치).
  const recoveredGap = useMemo(() => {
    if (!summary) return 0;
    return toNumber(summary.total_actual) - toNumber(summary.total_declared);
  }, [summary]);

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xlsm,.pdf",
    multiple: false,
    showUploadList: false,
    beforeUpload: (file) => {
      setPendingFile(file);
      setUploadResult(null);
      return false;
    },
  };

  const handleUpload = async () => {
    if (!pendingFile) {
      message.warning("업로드할 면장 엑셀/PDF 파일을 먼저 선택하세요");
      return;
    }
    setUploading(true);
    try {
      const res = await uploadCustoms(pendingFile, uploadCompany);
      setUploadResult(res);
      message.success(
        `면장 업로드 완료 — 신규 ${res.inserted}건 / 갱신 ${res.updated}건`,
      );
      setPendingFile(null);
      setPage(1);
      void loadData();
    } catch (err: unknown) {
      const detail = extractErrorDetail(err, "면장 업로드 실패", {
        useAxiosMessage: true,
      });
      message.error(detail);
    } finally {
      setUploading(false);
    }
  };

  const columns: ColumnsType<CustomsDeclarationOut> = [
    {
      title: "신고번호",
      dataIndex: "declaration_number",
      key: "declaration_number",
      width: 160,
      render: (v: string | null) =>
        v ? <Text code>{v}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: "품명",
      dataIndex: "product",
      key: "product",
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "신고가",
      dataIndex: "declared_price",
      key: "declared_price",
      align: "right",
      width: 140,
      render: (v: string | null, row) => (
        <Text style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatMoney(v)}
          {row.currency ? (
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
              {row.currency}
            </Text>
          ) : null}
        </Text>
      ),
    },
    {
      title: `실가 (÷${ratio})`,
      dataIndex: "actual_price",
      key: "actual_price",
      align: "right",
      width: 150,
      render: (v: string | null) => (
        <Text
          strong
          style={{ fontVariantNumeric: "tabular-nums", color: "#cf1322" }}
        >
          {formatMoney(v)}
        </Text>
      ),
    },
    {
      title: "재고",
      dataIndex: "stock_qty",
      key: "stock_qty",
      align: "right",
      width: 90,
      render: (v: number | null) =>
        v == null ? (
          <Text type="secondary">—</Text>
        ) : (
          NUMBER_FORMATTER.format(v)
        ),
    },
    {
      title: "회사",
      dataIndex: "company_label",
      key: "company_label",
      width: 110,
      render: (v: string | null) =>
        v ? <Tag color="geekblue">{v}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: "신고일자",
      dataIndex: "declared_at",
      key: "declared_at",
      width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
  ];

  return (
    <div style={{ maxWidth: 1180 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          면장 (통관신고) 데이터
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          면장 엑셀 또는 PDF를 업로드해 신고번호 · 신고가 · 재고를 수집합니다.
          동일 신고번호는 자동 갱신됩니다.
        </Paragraph>
      </div>

      {/* 75% 역산 관계 안내 — 페이지의 핵심 규칙을 명시적으로 노출 */}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message={`신고가는 실가의 ${ratioPercent}% 입니다`}
        description={
          <Text>
            관세 절감을 위해 면장에는 실제 가치의 {ratioPercent}%만 신고됩니다.
            따라서{" "}
            <Text strong style={{ color: "#cf1322" }}>
              실가 = 신고가 ÷ {ratio}
            </Text>{" "}
            로 역산하여 표시합니다.
          </Text>
        }
      />

      {errorMsg && (
        <Alert
          type="error"
          showIcon
          message={errorMsg}
          style={{ marginBottom: 16 }}
          closable
          onClose={() => setErrorMsg(null)}
        />
      )}

      {/* 업로드 카드 */}
      <Card
        size="small"
        title="면장 엑셀/PDF 업로드"
        style={{ marginBottom: 20 }}
        extra={
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              적재 회사
            </Text>
            <Select<DistributionCompany>
              value={uploadCompany}
              onChange={setUploadCompany}
              options={COMPANY_SELECT_OPTIONS}
              style={{ width: 160 }}
              disabled={uploading}
              size="small"
            />
          </Space>
        }
      >
        <Dragger {...uploadProps} style={{ padding: "8px 4px" }}>
          <p className="ant-upload-drag-icon" style={{ margin: 0 }}>
            <InboxOutlined />
          </p>
          <p className="ant-upload-text" style={{ fontSize: 14, margin: 4 }}>
            면장 엑셀(.xlsx/.xlsm) 또는 PDF(.pdf)를 끌어다 놓거나 클릭해서 선택
          </p>
          <p className="ant-upload-hint" style={{ fontSize: 12 }}>
            컬럼 매핑은 실제 면장 양식 확정 후 조정됩니다 (헤더 텍스트 기반 자동
            인식). PDF는 표 추출을 우선 시도하고, 실패 시 본문 텍스트를
            분석합니다.
          </p>
        </Dragger>

        {pendingFile && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: "#fafafa",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Space>
              <Text strong>선택된 파일:</Text>
              <Text>{pendingFile.name}</Text>
            </Space>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={uploading}
              onClick={handleUpload}
            >
              업로드 시작
            </Button>
          </div>
        )}

        {uploadResult && (
          <Alert
            type={uploadResult.parsed > 0 ? "success" : "warning"}
            showIcon
            style={{ marginTop: 12 }}
            message={`파싱 ${uploadResult.parsed}건 · 신규 ${uploadResult.inserted}건 · 갱신 ${uploadResult.updated}건`}
            description={
              uploadResult.warnings.length > 0 ? (
                <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 13 }}>
                  {uploadResult.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              ) : uploadResult.parsed === 0 ? (
                "추출된 행이 없습니다. 면장 양식의 헤더(신고번호/신고가 등)를 확인하세요."
              ) : null
            }
          />
        )}
      </Card>

      {/* 집계 카드 — 신고가 vs 실가 역산 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="총 신고가 (면장 기재)"
              value={summary ? formatMoney(summary.total_declared) : "—"}
              valueStyle={{ fontVariantNumeric: "tabular-nums" }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              면장 {summary?.count ?? 0}건 합계
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title={`총 실가 (역산 ÷${ratio})`}
              value={summary ? formatMoney(summary.total_actual) : "—"}
              valueStyle={{
                color: "#cf1322",
                fontVariantNumeric: "tabular-nums",
              }}
              prefix={<RiseOutlined />}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              신고가 ÷ {ratio} 로 복원한 실제 가치
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic
              title="역산 차액 (실가 − 신고가)"
              value={summary ? formatMoney(recoveredGap) : "—"}
              valueStyle={{
                color: "#d46b08",
                fontVariantNumeric: "tabular-nums",
              }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              신고가에 가려진 숨은 가치
            </Text>
          </Card>
        </Col>
      </Row>

      {/* 목록 */}
      <Card
        size="small"
        title="면장 목록"
        extra={
          <Space wrap>
            <Select<DistributionCompany | "all">
              value={companyFilter}
              onChange={(v) => {
                setCompanyFilter(v);
                setPage(1);
              }}
              options={COMPANY_FILTER_OPTIONS}
              style={{ width: 180 }}
              size="small"
            />
            <Input.Search
              placeholder="신고번호 / 품명 / BL번호"
              allowClear
              size="small"
              style={{ width: 220 }}
              onSearch={(v) => {
                setSearch(v);
                setPage(1);
              }}
            />
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={() => void loadData()}
              loading={loading}
            >
              새로고침
            </Button>
          </Space>
        }
      >
        <Table<CustomsDeclarationOut>
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          size="small"
          scroll={{ x: 880 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: ["20", "50", "100"],
            showTotal: (t) => `총 ${t.toLocaleString("ko-KR")}건`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>
    </div>
  );
}
