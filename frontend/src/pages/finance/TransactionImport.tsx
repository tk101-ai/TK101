import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Result,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  FileExcelOutlined,
  InboxOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { UploadProps } from "antd";
import {
  confirmImport,
  getAdapters,
  previewImport,
  type BankAdapter,
  type ImportPreviewOut,
  type ImportResultOut,
} from "../../api/bankImport";
import {
  ACCOUNT_TYPE_OPTIONS,
  CURRENCY_OPTIONS,
  listAccounts,
  type Account,
  type AccountType,
  type Currency,
} from "../../api/accounts";
import { extractErrorDetail as extractDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

// 행 단위 결정. preview 후 사용자가 어떻게 처리할지 선택한다.
type RowDecision = "use_existing" | "create_new" | "skip";

interface ImportRow {
  uid: string;
  file: File;
  loading: boolean;
  preview: ImportPreviewOut | null;
  errorMessage: string | null;
  decision: RowDecision;
  selectedAccountId: string | null;
  // create_new 결정 시 사용할 신규 계좌 폼 값
  newAccountForm: {
    bank_name: string;
    account_number: string;
    account_holder: string;
    account_type: AccountType | null;
    currency: Currency;
    business_registration_no: string;
    alias: string;
  };
  result: ImportResultOut | null;
  importErrorMessage: string | null;
}

function extractErrorDetail(err: unknown, fallback: string): string {
  return extractDetail(err, fallback, {
    statusMessages: {
      404: "백엔드 라우터가 아직 등록되지 않았습니다 (Wave 5 예정).",
    },
    useAxiosMessage: true,
  });
}

function makeUid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isExcelFile(file: File): boolean {
  const name = file.name.toLowerCase();
  if (name.startsWith("~$")) return false; // 엑셀 임시파일
  return name.endsWith(".xlsx");
}

function defaultNewAccountForm(preview: ImportPreviewOut | null): ImportRow["newAccountForm"] {
  const meta = preview?.account_meta ?? {};
  const currency =
    typeof meta.currency === "string" && meta.currency.length > 0
      ? (meta.currency as Currency)
      : "KRW";
  const accountType =
    typeof meta.account_type === "string" && meta.account_type.length > 0
      ? (meta.account_type as AccountType)
      : null;
  return {
    bank_name: (preview?.bank_name as string) || (meta.bank_name as string) || "",
    account_number: (meta.account_number as string) || "",
    account_holder: (meta.account_holder as string) || "",
    account_type: accountType,
    currency,
    business_registration_no: (meta.business_registration_no as string) || "",
    alias: "",
  };
}

export default function TransactionImport() {
  const [adapters, setAdapters] = useState<BankAdapter[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [errorDetailRow, setErrorDetailRow] = useState<ImportRow | null>(null);

  const loadMeta = useCallback(async () => {
    try {
      const [adp, accs] = await Promise.all([getAdapters(), listAccounts()]);
      setAdapters(adp);
      setAccounts(accs);
    } catch (err: unknown) {
      // 백엔드 라우터 미등록 상황을 사용자에게 안내. 페이지 자체는 동작 가능.
      message.warning(
        extractErrorDetail(err, "은행 어댑터 또는 계좌 목록 로딩 실패"),
      );
    }
  }, []);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  const accountOptions = useMemo(
    () =>
      accounts.map((a) => ({
        value: a.id,
        label: `${a.bank_name} · ${a.account_number}${a.alias ? ` (${a.alias})` : ""}`,
      })),
    [accounts],
  );

  const handleFiles = useCallback(async (files: File[]) => {
    const valid = files.filter(isExcelFile);
    const skipped = files.length - valid.length;
    if (skipped > 0) {
      message.warning(`엑셀(.xlsx)이 아니거나 임시파일이라 ${skipped}건 제외했습니다`);
    }
    if (valid.length === 0) return;

    const newRows: ImportRow[] = valid.map((file) => ({
      uid: makeUid(),
      file,
      loading: true,
      preview: null,
      errorMessage: null,
      decision: "skip",
      selectedAccountId: null,
      newAccountForm: defaultNewAccountForm(null),
      result: null,
      importErrorMessage: null,
    }));
    setRows((prev) => [...prev, ...newRows]);

    // 미리보기 병렬 호출. 각 행의 상태는 uid 로 매칭.
    await Promise.all(
      newRows.map(async (row) => {
        try {
          const preview = await previewImport(row.file);
          setRows((prev) =>
            prev.map((r) =>
              r.uid === row.uid
                ? {
                    ...r,
                    loading: false,
                    preview,
                    decision: preview.existing_account_id
                      ? "use_existing"
                      : "create_new",
                    selectedAccountId: preview.existing_account_id,
                    newAccountForm: defaultNewAccountForm(preview),
                  }
                : r,
            ),
          );
        } catch (err: unknown) {
          setRows((prev) =>
            prev.map((r) =>
              r.uid === row.uid
                ? {
                    ...r,
                    loading: false,
                    errorMessage: extractErrorDetail(err, "미리보기 실패"),
                  }
                : r,
            ),
          );
        }
      }),
    );
  }, []);

  const handleRemove = (uid: string) => {
    setRows((prev) => prev.filter((r) => r.uid !== uid));
  };

  const updateRow = (uid: string, patch: Partial<ImportRow>) => {
    setRows((prev) => prev.map((r) => (r.uid === uid ? { ...r, ...patch } : r)));
  };

  const updateNewAccountField = (
    uid: string,
    field: keyof ImportRow["newAccountForm"],
    value: string | null,
  ) => {
    setRows((prev) =>
      prev.map((r) =>
        r.uid === uid
          ? {
              ...r,
              newAccountForm: { ...r.newAccountForm, [field]: value ?? "" },
            }
          : r,
      ),
    );
  };

  const readyRows = useMemo(
    () =>
      rows.filter(
        (r) => !r.loading && r.preview && !r.errorMessage && r.decision !== "skip",
      ),
    [rows],
  );

  const totalEstimated = useMemo(
    () =>
      readyRows.reduce((acc, r) => acc + (r.preview?.transaction_count ?? 0), 0),
    [readyRows],
  );

  const handleConfirmAll = async () => {
    if (readyRows.length === 0) {
      message.info("처리할 파일이 없습니다");
      return;
    }
    setConfirming(true);
    try {
      await Promise.all(
        readyRows.map(async (row) => {
          try {
            const payload =
              row.decision === "use_existing"
                ? {
                    account_id: row.selectedAccountId ?? undefined,
                    create_account: false,
                    on_duplicate: "skip" as const,
                  }
                : {
                    create_account: true,
                    on_duplicate: "skip" as const,
                  };
            const result = await confirmImport(row.file, payload);
            updateRow(row.uid, { result, importErrorMessage: null });
          } catch (err: unknown) {
            updateRow(row.uid, {
              importErrorMessage: extractErrorDetail(err, "import 실패"),
            });
          }
        }),
      );
      setResultModalOpen(true);
    } finally {
      setConfirming(false);
    }
  };

  const uploadProps: UploadProps = {
    multiple: true,
    showUploadList: false,
    accept: ".xlsx",
    beforeUpload: (_file, fileList) => {
      void handleFiles(fileList);
      return Upload.LIST_IGNORE; // 우리가 관리하므로 antd 내부 큐에서 제외
    },
  };

  // 결과 합계
  const resultSummary = useMemo(() => {
    const results = rows.map((r) => r.result).filter((r): r is ImportResultOut => r !== null);
    const imported = results.reduce((a, r) => a + (r.imported_count || 0), 0);
    const duplicate = results.reduce((a, r) => a + (r.duplicate_count || 0), 0);
    const errors = results.reduce((a, r) => a + (r.error_count || 0), 0);
    const failed = rows.filter((r) => r.importErrorMessage).length;
    return { imported, duplicate, errors, failed, fileCount: results.length };
  }, [rows]);

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          거래 가져오기
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          은행 거래 엑셀을 업로드하면 자동으로 은행·계좌를 인식해 거래내역으로 등록합니다.
          {adapters.length > 0 && (
            <Text type="secondary"> · 지원 은행 {adapters.length}곳</Text>
          )}
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 20 }}>
        <Dragger {...uploadProps} style={{ padding: "12px 8px" }}>
          <p className="ant-upload-drag-icon" style={{ margin: 0 }}>
            <InboxOutlined />
          </p>
          <p className="ant-upload-text" style={{ fontSize: 14, marginBottom: 4 }}>
            엑셀 파일을 끌어다 놓거나 클릭해서 선택
          </p>
          <p className="ant-upload-hint" style={{ fontSize: 12 }}>
            .xlsx 만 지원. 여러 파일을 한 번에 올릴 수 있습니다.
          </p>
        </Dragger>
      </Card>

      {rows.length === 0 ? (
        <Empty description="아직 업로드된 파일이 없습니다" />
      ) : (
        <>
          <Space style={{ marginBottom: 12 }}>
            <Tag color="blue">파일 {rows.length}개</Tag>
            <Tag color="green">처리 예정 거래 약 {totalEstimated}건</Tag>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={confirming}
              disabled={readyRows.length === 0}
              onClick={handleConfirmAll}
            >
              일괄 적용
            </Button>
            <Button onClick={() => setRows([])} disabled={confirming}>
              모두 비우기
            </Button>
          </Space>

          <div style={{ display: "grid", gap: 12 }}>
            {rows.map((row) => (
              <Card
                key={row.uid}
                size="small"
                title={
                  <Space>
                    <FileExcelOutlined style={{ color: "#52c41a" }} />
                    <Text strong>{row.file.name}</Text>
                    {row.preview?.bank_name && (
                      <Tag color="blue">{row.preview.bank_name}</Tag>
                    )}
                    {row.result && (
                      <Tag color="green" icon={<CheckCircleOutlined />}>
                        적용 완료
                      </Tag>
                    )}
                    {row.importErrorMessage && (
                      <Tag color="red" icon={<WarningOutlined />}>
                        실패
                      </Tag>
                    )}
                  </Space>
                }
                extra={
                  <Button
                    type="link"
                    size="small"
                    danger
                    onClick={() => handleRemove(row.uid)}
                    disabled={confirming}
                  >
                    제거
                  </Button>
                }
              >
                {row.loading && <Spin tip="분석 중…" />}

                {row.errorMessage && (
                  <Alert
                    type="error"
                    showIcon
                    message="미리보기 실패"
                    description={row.errorMessage}
                  />
                )}

                {row.preview && (
                  <ImportPreviewBody
                    row={row}
                    accountOptions={accountOptions}
                    onDecisionChange={(decision) => updateRow(row.uid, { decision })}
                    onAccountChange={(id) =>
                      updateRow(row.uid, { selectedAccountId: id })
                    }
                    onNewAccountFieldChange={(field, value) =>
                      updateNewAccountField(row.uid, field, value)
                    }
                    onShowErrors={() => setErrorDetailRow(row)}
                  />
                )}
              </Card>
            ))}
          </div>
        </>
      )}

      <Modal
        title="가져오기 결과"
        open={resultModalOpen}
        onCancel={() => setResultModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setResultModalOpen(false)}>
            닫기
          </Button>,
          <Button
            key="reset"
            type="primary"
            icon={<ReloadOutlined />}
            onClick={() => {
              setRows([]);
              setResultModalOpen(false);
            }}
          >
            새로 가져오기
          </Button>,
        ]}
        width={640}
      >
        <Result
          status={resultSummary.failed > 0 ? "warning" : "success"}
          title={
            resultSummary.failed > 0
              ? `${resultSummary.fileCount}개 적용, ${resultSummary.failed}개 실패`
              : `${resultSummary.fileCount}개 파일 적용 완료`
          }
          subTitle={
            <Space size="large" wrap>
              <span>
                신규 <Text strong>{resultSummary.imported}</Text>건
              </span>
              <span>
                중복 <Text strong>{resultSummary.duplicate}</Text>건
              </span>
              <span>
                에러 <Text strong>{resultSummary.errors}</Text>건
              </span>
            </Space>
          }
        />
      </Modal>

      <Modal
        title={`에러 상세 — ${errorDetailRow?.file.name ?? ""}`}
        open={errorDetailRow !== null}
        onCancel={() => setErrorDetailRow(null)}
        footer={[
          <Button key="close" onClick={() => setErrorDetailRow(null)}>
            닫기
          </Button>,
        ]}
        width={720}
      >
        {errorDetailRow?.result?.errors?.length ? (
          <div style={{ maxHeight: 360, overflow: "auto" }}>
            {errorDetailRow.result.errors.map((e, i) => (
              <Alert
                key={i}
                type="error"
                style={{ marginBottom: 6 }}
                message={
                  <Text style={{ fontSize: 12 }}>
                    {typeof e.row_number === "number" ? `행 ${e.row_number}: ` : ""}
                    {e.reason}
                  </Text>
                }
              />
            ))}
          </div>
        ) : (
          <Empty description="에러 상세가 없습니다" />
        )}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 행 본문 — 인라인 컴포넌트
// ---------------------------------------------------------------------------

interface PreviewBodyProps {
  row: ImportRow;
  accountOptions: { value: string; label: string }[];
  onDecisionChange: (decision: RowDecision) => void;
  onAccountChange: (id: string | null) => void;
  onNewAccountFieldChange: (
    field: keyof ImportRow["newAccountForm"],
    value: string | null,
  ) => void;
  onShowErrors: () => void;
}

function ImportPreviewBody({
  row,
  accountOptions,
  onDecisionChange,
  onAccountChange,
  onNewAccountFieldChange,
  onShowErrors,
}: PreviewBodyProps) {
  const preview = row.preview;
  if (!preview) return null;
  const result = row.result;
  const importError = row.importErrorMessage;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Space size={8} wrap>
        <Badge
          count={preview.transaction_count}
          showZero
          color="blue"
          overflowCount={9999}
        >
          <Tag style={{ marginRight: 0 }}>거래</Tag>
        </Badge>
        <Badge
          count={preview.duplicate_count_estimate}
          showZero
          color="orange"
          overflowCount={9999}
        >
          <Tag style={{ marginRight: 0 }}>중복 예상</Tag>
        </Badge>
        {preview.account_meta.account_number && (
          <Tag>계좌 {String(preview.account_meta.account_number)}</Tag>
        )}
        {preview.account_meta.account_holder && (
          <Tag>예금주 {String(preview.account_meta.account_holder)}</Tag>
        )}
        {preview.account_meta.period_label && (
          <Tag color="purple">{String(preview.account_meta.period_label)}</Tag>
        )}
      </Space>

      {preview.parse_warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`경고 ${preview.parse_warnings.length}건`}
          description={
            <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 12 }}>
              {preview.parse_warnings.slice(0, 5).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          }
        />
      )}
      {preview.parse_errors.length > 0 && (
        <Alert
          type="error"
          showIcon
          message={`파싱 오류 ${preview.parse_errors.length}건`}
          description={
            <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 12 }}>
              {preview.parse_errors.slice(0, 5).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          }
        />
      )}

      <Space size={8} wrap>
        <Tag
          color={row.decision === "use_existing" ? "blue" : "default"}
          style={{ cursor: preview.existing_account_id ? "pointer" : "not-allowed", opacity: preview.existing_account_id ? 1 : 0.5 }}
          onClick={() =>
            preview.existing_account_id && onDecisionChange("use_existing")
          }
        >
          기존 계좌에 추가
        </Tag>
        <Tag
          color={row.decision === "create_new" ? "green" : "default"}
          style={{ cursor: "pointer" }}
          onClick={() => onDecisionChange("create_new")}
        >
          새 계좌 등록 후 추가
        </Tag>
        <Tag
          color={row.decision === "skip" ? "red" : "default"}
          style={{ cursor: "pointer" }}
          onClick={() => onDecisionChange("skip")}
        >
          이 파일 건너뛰기
        </Tag>
      </Space>

      {row.decision === "use_existing" && (
        <Form layout="vertical" style={{ margin: 0 }}>
          <Form.Item label="대상 계좌" style={{ marginBottom: 0 }}>
            <Select
              value={row.selectedAccountId ?? undefined}
              onChange={(v) => onAccountChange(v ?? null)}
              options={accountOptions}
              placeholder="기존 계좌 선택"
              showSearch
              filterOption={(input, opt) =>
                (opt?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              style={{ width: "100%" }}
            />
          </Form.Item>
          {preview.similar_accounts.length > 0 && !preview.existing_account_id && (
            <Paragraph type="secondary" style={{ marginTop: 6, fontSize: 12 }}>
              유사 계좌 후보: {preview.similar_accounts
                .map((s) => `${s.account_number} (${Math.round(s.similarity * 100)}%)`)
                .join(", ")}
            </Paragraph>
          )}
        </Form>
      )}

      {row.decision === "create_new" && (
        <Card size="small" style={{ background: "#fafafa" }}>
          <Form layout="vertical" style={{ margin: 0 }}>
            <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr 1fr" }}>
              <Form.Item label="은행명" style={{ marginBottom: 0 }} required>
                <Input
                  value={row.newAccountForm.bank_name}
                  onChange={(e) =>
                    onNewAccountFieldChange("bank_name", e.target.value)
                  }
                />
              </Form.Item>
              <Form.Item label="계좌번호" style={{ marginBottom: 0 }} required>
                <Input
                  value={row.newAccountForm.account_number}
                  onChange={(e) =>
                    onNewAccountFieldChange("account_number", e.target.value)
                  }
                />
              </Form.Item>
              <Form.Item label="예금주" style={{ marginBottom: 0 }} required>
                <Input
                  value={row.newAccountForm.account_holder}
                  onChange={(e) =>
                    onNewAccountFieldChange("account_holder", e.target.value)
                  }
                />
              </Form.Item>
              <Form.Item label="계좌 종류" style={{ marginBottom: 0 }}>
                <Select
                  value={row.newAccountForm.account_type ?? undefined}
                  options={ACCOUNT_TYPE_OPTIONS}
                  onChange={(v) =>
                    onNewAccountFieldChange("account_type", (v as string) ?? null)
                  }
                  allowClear
                  placeholder="선택"
                />
              </Form.Item>
              <Form.Item label="통화" style={{ marginBottom: 0 }}>
                <Select
                  value={row.newAccountForm.currency}
                  options={CURRENCY_OPTIONS}
                  onChange={(v) =>
                    onNewAccountFieldChange("currency", v as string)
                  }
                />
              </Form.Item>
              <Form.Item label="별칭(선택)" style={{ marginBottom: 0 }}>
                <Input
                  value={row.newAccountForm.alias}
                  onChange={(e) => onNewAccountFieldChange("alias", e.target.value)}
                  placeholder="예: 운영자금 계좌"
                />
              </Form.Item>
            </div>
            <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
              백엔드는 파일에서 추출한 메타데이터를 기준으로 신규 계좌를 자동 생성합니다.
              위 값은 참고용 미리보기입니다.
            </Paragraph>
          </Form>
        </Card>
      )}

      {result && (
        <Alert
          type={result.error_count > 0 ? "warning" : "success"}
          showIcon
          message={`적용 완료 — 신규 ${result.imported_count}건 · 중복 ${result.duplicate_count}건 · 에러 ${result.error_count}건`}
          action={
            result.error_count > 0 ? (
              <Button size="small" onClick={onShowErrors}>
                에러 상세
              </Button>
            ) : null
          }
        />
      )}

      {importError && (
        <Alert type="error" showIcon message="가져오기 실패" description={importError} />
      )}
    </div>
  );
}
