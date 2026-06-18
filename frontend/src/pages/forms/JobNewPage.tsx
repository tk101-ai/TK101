import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  message,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  CloudUploadOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import {
  addNasSourcesToJob,
  getFormJob,
  runJobMapping,
  uploadJobSource,
  type FormDataSource,
  type FormJobDetail,
} from "../../api/forms";
import type { NasSearchHit } from "../../api/nas";
import SourcePicker from "../../components/forms/SourcePicker";

const { Text, Paragraph } = Typography;

/**
 * [3] 자료 수집 — FR-03.
 * 사용자 업로드 + NAS 검색 통합. 자료 수집 후 [4] 매핑 실행.
 */
export default function JobNewPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<FormJobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [autoQuery, setAutoQuery] = useState("");

  const refresh = async () => {
    try {
      const d = await getFormJob(id);
      setDetail(d);
    } catch {
      message.error("작성 잡 정보를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // id 변경 시 작업 상세 재요청 (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handlePickNas = async (hits: NasSearchHit[]) => {
    setBusy(true);
    try {
      // 검색결과 hit.id 는 doc_id→UUID 인코딩이라 조회 키로 못 쓴다. 안정적인 path 로 선택.
      await addNasSourcesToJob(id, { nasPaths: hits.map((h) => h.path) });
      message.success(`NAS 자료 ${hits.length}개 추가`);
      await refresh();
    } catch {
      message.error("NAS 자료 추가 실패");
    } finally {
      setBusy(false);
    }
  };

  // AI 자동 자료 수집: 직접 입력한 쿼리 또는 양식 변수 기반 자동 쿼리로 NAS 검색.
  const handleAutoCollect = async (fromTemplate: boolean) => {
    const q = autoQuery.trim();
    if (!fromTemplate && !q) {
      message.warning("검색어를 입력하거나 ‘양식 기반 자동 검색’을 사용하세요");
      return;
    }
    setBusy(true);
    try {
      const res = await addNasSourcesToJob(id, {
        autoQuery: fromTemplate ? undefined : q,
        autoQueryFromTemplate: fromTemplate,
      });
      if (res.total === 0) {
        message.info("관련 NAS 자료를 찾지 못했습니다");
      } else {
        message.success(`NAS 자료 ${res.total}건 자동 수집`);
      }
      await refresh();
    } catch {
      message.error("자동 자료 수집 실패");
    } finally {
      setBusy(false);
    }
  };

  const handlePickUpload = async (files: File[]) => {
    setBusy(true);
    const results = await Promise.allSettled(
      files.map((f) => uploadJobSource(id, f)),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const failed = files.length - ok;
    if (failed === 0) {
      message.success(`${ok}개 자료 업로드 완료`);
    } else if (ok === 0) {
      message.error(`자료 업로드 실패 (${failed}개)`);
    } else {
      message.warning(`${ok}개 성공 · ${failed}개 실패`);
    }
    await refresh();
    setBusy(false);
  };

  const handleRunMapping = async () => {
    if (!detail) return;
    if (detail.sources.length === 0) {
      message.warning("자료를 1개 이상 추가해야 매핑을 실행할 수 있습니다");
      return;
    }
    setBusy(true);
    try {
      await runJobMapping(id);
      message.success("매핑 완료 — 검수 단계로 이동");
      navigate(`/forms/jobs/${id}/review`);
    } catch {
      message.error("매핑 실행 실패");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 64 }}>
        <Spin />
      </div>
    );
  }
  if (!detail) {
    return <Empty description="작성 잡 정보가 없습니다" style={{ marginTop: 64 }} />;
  }

  return (
    <div style={{ maxWidth: 1080 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
          자료 수집{" "}
          <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
            v0.1 · 3단계 / 5
          </Text>
        </h2>
        <Text type="secondary">
          양식 「{detail.template.name}」 · 변수 {detail.template.variables.length}개
        </Text>
      </div>

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <ThunderboltOutlined />
            <span>AI 자동 자료 수집 (NAS)</span>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
          회사 NAS 문서(벡터검색)에서 관련 자료를 자동으로 찾아 추가합니다. 주제를 입력하거나,
          이 양식 변수 기반으로 자동 검색하세요.
        </Paragraph>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            placeholder="예: 신세계백화점 SNS 운영 보고서"
            value={autoQuery}
            onChange={(e) => setAutoQuery(e.target.value)}
            onPressEnter={() => handleAutoCollect(false)}
            disabled={busy}
            allowClear
          />
          <Button
            type="primary"
            icon={<FileSearchOutlined />}
            onClick={() => handleAutoCollect(false)}
            loading={busy}
          >
            검색해서 추가
          </Button>
        </Space.Compact>
        <Button
          type="link"
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => handleAutoCollect(true)}
          disabled={busy}
          style={{ paddingLeft: 0, marginTop: 4 }}
        >
          양식 변수 기반 자동 검색
        </Button>
      </Card>

      <Card
        title={
          <Space>
            <FileSearchOutlined />
            <span>수집된 자료 ({detail.sources.length}개)</span>
          </Space>
        }
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setPickerOpen(true)}
            disabled={busy}
          >
            자료 추가
          </Button>
        }
      >
        {detail.sources.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="자료를 1개 이상 추가하세요 (NAS 검색 또는 업로드)"
          />
        ) : (
          <List
            size="small"
            dataSource={detail.sources}
            renderItem={(s: FormDataSource) => (
              <List.Item>
                <List.Item.Meta
                  avatar={
                    s.kind === "user_upload" ? <CloudUploadOutlined /> : <FileSearchOutlined />
                  }
                  title={
                    <Space>
                      <span>
                        {s.display_name ??
                          s.upload_path ??
                          s.nas_file_id ??
                          "(이름 없음)"}
                      </span>
                      <Tag color={s.kind === "nas_file" ? "blue" : "green"}>
                        {s.kind === "nas_file"
                          ? "NAS"
                          : s.kind === "user_upload"
                            ? "업로드"
                            : s.kind}
                      </Tag>
                    </Space>
                  }
                  description={
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 11, margin: 0, wordBreak: "break-all" }}
                    >
                      {s.upload_path ?? s.nas_file_id ?? "-"}
                    </Paragraph>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
        <Button onClick={() => navigate(`/forms/templates/${detail.template.id}/review`)}>
          이전 단계 (변수 검수)
        </Button>
        <Button
          type="primary"
          onClick={handleRunMapping}
          loading={busy}
          disabled={detail.sources.length === 0}
        >
          매핑 실행 (4단계)
        </Button>
      </div>

      <SourcePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPickNas={(hits) => handlePickNas(hits)}
        onPickUpload={(files) => handlePickUpload(files)}
      />
    </div>
  );
}
