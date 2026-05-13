import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Empty,
  List,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Typography,
  Upload,
  message,
} from "antd";
import { DeleteOutlined, DownloadOutlined, InboxOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import {
  deleteAttachment,
  getAttachments,
  uploadAttachment,
  type AttachmentItem,
} from "../../api/transactions";
import { extractErrorDetail } from "../../utils/errorUtils";

interface AttachmentModalProps {
  open: boolean;
  transactionId: string | null;
  onClose: () => void;
}

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.gif,.heic";
const MAX_BYTES = 10 * 1024 * 1024;

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

// 영수증 첨부 모달. 백엔드: /api/transactions/{id}/attachments
export default function AttachmentModal({
  open,
  transactionId,
  onClose,
}: AttachmentModalProps) {
  const [items, setItems] = useState<AttachmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const reload = useCallback(async () => {
    if (!transactionId) return;
    setLoading(true);
    try {
      const data = await getAttachments(transactionId);
      setItems(data);
    } catch (err) {
      message.error(extractErrorDetail(err, "첨부 목록을 불러오지 못했습니다"));
    } finally {
      setLoading(false);
    }
  }, [transactionId]);

  useEffect(() => {
    if (open && transactionId) {
      // 모달 open + 대상 변경 시 첨부 목록 비동기 로드.
      // react-hooks v7 set-state-in-effect 는 일반 데이터 로딩 패턴을 모두
      // 위반으로 잡으므로, 의도된 fetch+setState 패턴임을 명시한다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void reload();
    } else {
      setItems([]);
    }
  }, [open, transactionId, reload]);

  const handleUpload = async (file: File): Promise<boolean> => {
    if (!transactionId) return false;
    if (file.size > MAX_BYTES) {
      message.error("파일 크기는 10MB를 초과할 수 없습니다");
      return false;
    }
    setUploading(true);
    try {
      await uploadAttachment(transactionId, file);
      message.success("첨부 업로드 완료");
      await reload();
    } catch (err) {
      message.error(extractErrorDetail(err, "첨부 업로드 실패"));
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleDelete = async (filename: string) => {
    if (!transactionId) return;
    try {
      await deleteAttachment(transactionId, filename);
      message.success("첨부 삭제 완료");
      await reload();
    } catch (err) {
      message.error(extractErrorDetail(err, "첨부 삭제 실패"));
    }
  };

  return (
    <Modal
      title="영수증 / 첨부 관리"
      open={open}
      onCancel={onClose}
      footer={null}
      width={620}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Upload.Dragger
          accept={ACCEPT}
          showUploadList={false}
          multiple={false}
          beforeUpload={(file: UploadFile & File) => handleUpload(file)}
          disabled={uploading || !transactionId}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">클릭하거나 파일을 드래그하여 업로드</p>
          <p className="ant-upload-hint">
            PDF / PNG / JPG / WebP / GIF / HEIC, 최대 10MB
          </p>
        </Upload.Dragger>

        <Spin spinning={loading}>
          {items.length === 0 ? (
            <Empty description="첨부 파일 없음" />
          ) : (
            <List<AttachmentItem>
              dataSource={items}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="download"
                      type="link"
                      icon={<DownloadOutlined />}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      다운로드
                    </Button>,
                    <Popconfirm
                      key="delete"
                      title="첨부 삭제"
                      description="이 파일을 삭제할까요?"
                      okText="삭제"
                      cancelText="취소"
                      onConfirm={() => handleDelete(item.filename)}
                    >
                      <Button type="link" danger icon={<DeleteOutlined />}>
                        삭제
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.filename}
                    description={
                      <Typography.Text type="secondary">
                        {item.content_type} · {formatSize(item.size)} ·{" "}
                        {new Date(item.uploaded_at).toLocaleString("ko-KR")}
                      </Typography.Text>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Space>
    </Modal>
  );
}
