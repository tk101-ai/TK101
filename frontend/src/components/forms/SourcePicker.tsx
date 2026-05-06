import { useState } from "react";
import {
  Button,
  Empty,
  Input,
  List,
  message,
  Modal,
  Spin,
  Tabs,
  Tag,
  Upload,
} from "antd";
import { CloudUploadOutlined, InboxOutlined, SearchOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { searchNasText, type NasSearchHit } from "../../api/nas";

interface SourcePickerProps {
  open: boolean;
  onClose: () => void;
  onPickNas: (hits: NasSearchHit[]) => void;
  onPickUpload: (files: File[]) => void;
}

/**
 * NAS 의미 검색 + 사용자 업로드 통합 모달 (FR-03).
 * 양식 작성 화면에서 별도 페이지 이동 없이 자료를 수집할 수 있게 함.
 */
export default function SourcePicker({
  open,
  onClose,
  onPickNas,
  onPickUpload,
}: SourcePickerProps) {
  const [tab, setTab] = useState<"nas" | "upload">("nas");

  // NAS 검색
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<NasSearchHit[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 업로드
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      message.info("검색어를 입력하세요");
      return;
    }
    setSearching(true);
    try {
      const res = await searchNasText(trimmed, 20);
      setResults(res.data.results);
    } catch {
      message.error("NAS 검색 실패");
    } finally {
      setSearching(false);
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleConfirm = () => {
    if (tab === "nas") {
      const picked = results.filter((r) => selectedIds.has(r.id));
      if (picked.length === 0) {
        message.info("자료를 1개 이상 선택하세요");
        return;
      }
      onPickNas(picked);
      reset();
      onClose();
    } else {
      const files = fileList
        .map((f) => f.originFileObj as File | undefined)
        .filter((f): f is File => !!f);
      if (files.length === 0) {
        message.info("파일을 1개 이상 선택하세요");
        return;
      }
      onPickUpload(files);
      reset();
      onClose();
    }
  };

  const reset = () => {
    setQuery("");
    setResults([]);
    setSelectedIds(new Set());
    setFileList([]);
  };

  return (
    <Modal
      open={open}
      onCancel={() => {
        reset();
        onClose();
      }}
      onOk={handleConfirm}
      title="자료 추가"
      okText="추가"
      cancelText="취소"
      width={760}
      destroyOnClose
    >
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as "nas" | "upload")}
        items={[
          {
            key: "nas",
            label: (
              <span>
                <SearchOutlined /> NAS 의미 검색
              </span>
            ),
            children: (
              <div>
                <Input.Search
                  enterButton="검색"
                  placeholder="예: 5월 캠페인 결과"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onSearch={handleSearch}
                  loading={searching}
                  style={{ marginBottom: 12 }}
                />
                {searching ? (
                  <div style={{ textAlign: "center", padding: 32 }}>
                    <Spin />
                  </div>
                ) : results.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="검색 결과 없음 (검색어를 입력하세요)"
                  />
                ) : (
                  <List
                    size="small"
                    dataSource={results}
                    style={{ maxHeight: 380, overflowY: "auto" }}
                    renderItem={(hit) => {
                      const checked = selectedIds.has(hit.id);
                      return (
                        <List.Item
                          style={{
                            cursor: "pointer",
                            background: checked ? "#e6f4ff" : undefined,
                            borderRadius: 4,
                            padding: "8px 12px",
                          }}
                          onClick={() => toggleSelect(hit.id)}
                          extra={<Tag color="blue">{hit.score.toFixed(2)}</Tag>}
                        >
                          <List.Item.Meta
                            title={
                              <span style={{ fontWeight: checked ? 600 : 400 }}>
                                {checked ? "✓ " : ""}
                                {hit.name}
                              </span>
                            }
                            description={
                              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                                {hit.path}
                              </div>
                            }
                          />
                        </List.Item>
                      );
                    }}
                  />
                )}
                <div style={{ marginTop: 8, color: "#8c8c8c", fontSize: 12 }}>
                  선택된 자료: {selectedIds.size}개
                </div>
              </div>
            ),
          },
          {
            key: "upload",
            label: (
              <span>
                <CloudUploadOutlined /> 사용자 업로드
              </span>
            ),
            children: (
              <div>
                <Upload.Dragger
                  multiple
                  accept=".pdf,.docx,.xlsx,.csv,.txt,.pptx"
                  fileList={fileList}
                  beforeUpload={() => false}
                  onChange={({ fileList: fl }) => setFileList(fl)}
                  onRemove={(file) => {
                    setFileList((curr) => curr.filter((f) => f.uid !== file.uid));
                  }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">자료 파일을 끌어다 놓거나 클릭해 선택</p>
                  <p className="ant-upload-hint" style={{ fontSize: 12 }}>
                    PDF / DOCX / PPTX / XLSX / CSV / TXT (30일 자동 삭제 · 이미지는 Phase 1+)
                  </p>
                </Upload.Dragger>
                <div style={{ marginTop: 8, color: "#8c8c8c", fontSize: 12 }}>
                  업로드 대기: {fileList.length}개
                </div>
              </div>
            ),
          },
        ]}
      />
      <div style={{ marginTop: 12, fontSize: 11, color: "#bfbfbf" }}>
        <Button
          type="link"
          size="small"
          onClick={() =>
            message.info("AI 외부 검색 (웹) 은 Phase 3 예정 — 현재 OFF")
          }
          style={{ padding: 0 }}
        >
          AI 외부 검색 (Phase 3, OFF)
        </Button>
      </div>
    </Modal>
  );
}
