import { Modal, Select, Space, Upload } from "antd";
import { type Account } from "../../../api/accounts";

// ---------------------------------------------------------------------------
// 거래내역 엑셀 업로드 모달
// ---------------------------------------------------------------------------

interface UploadModalProps {
  open: boolean;
  accounts: Account[];
  uploadAccountId: string;
  setUploadAccountId: (id: string) => void;
  onCancel: () => void;
  onUpload: (file: File) => boolean | Promise<boolean>;
}

export function UploadModal({
  open,
  accounts,
  uploadAccountId,
  setUploadAccountId,
  onCancel,
  onUpload,
}: UploadModalProps) {
  return (
    <Modal
      title="거래내역 엑셀 업로드"
      open={open}
      onCancel={onCancel}
      footer={null}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        <Select
          placeholder="업로드할 계좌 선택"
          style={{ width: "100%" }}
          value={uploadAccountId || undefined}
          onChange={setUploadAccountId}
          options={accounts.map((a) => ({
            label: `${a.bank_name} ${a.account_number}`,
            value: a.id,
          }))}
        />
        <Upload.Dragger
          accept=".xlsx,.xls"
          showUploadList={false}
          beforeUpload={(file) => onUpload(file as File)}
        >
          <p style={{ padding: "20px 0" }}>엑셀 파일을 드래그하거나 클릭하여 업로드</p>
        </Upload.Dragger>
      </Space>
    </Modal>
  );
}
