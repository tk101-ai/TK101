import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ColorPicker,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tree,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import type { DataNode } from "antd/es/tree";
import {
  createCategory,
  deleteCategory,
  listCategoriesTree,
  updateCategory,
  type CategoryCreate,
  type CategoryNode,
  type CategoryUpdate,
} from "../../api/categories";
import { useAuth } from "../../hooks/useAuth";
import {
  makeErrorExtractor,
  NOT_FOUND_MESSAGE,
  FORBIDDEN_MESSAGE,
} from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;

const extractErrorDetail = makeErrorExtractor({
  statusMessages: {
    404: NOT_FOUND_MESSAGE,
    403: FORBIDDEN_MESSAGE,
  },
  useAxiosMessage: true,
});

interface FormValues {
  name: string;
  code?: string;
  color?: string;
  parent_id?: string | null;
}

function nodeDepth(node: CategoryNode, root: CategoryNode[]): number {
  // children 트리를 BFS 로 깊이 계산
  for (const r of root) {
    if (r.id === node.id) return 1;
  }
  const findDepth = (curr: CategoryNode[], target: string, d: number): number => {
    for (const n of curr) {
      if (n.id === target) return d;
      const inner = findDepth(n.children, target, d + 1);
      if (inner > 0) return inner;
    }
    return 0;
  };
  return findDepth(root, node.id, 1);
}

function toTreeData(nodes: CategoryNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.id,
    title: (
      <Space size={6}>
        {n.color && (
          <span
            style={{
              display: "inline-block",
              width: 10,
              height: 10,
              borderRadius: 2,
              background: n.color,
            }}
          />
        )}
        <Text>{n.name}</Text>
        {n.code && <Text type="secondary" style={{ fontSize: 11 }}>[{n.code}]</Text>}
      </Space>
    ),
    children: n.children?.length ? toTreeData(n.children) : undefined,
  }));
}

function findNode(nodes: CategoryNode[], id: string): CategoryNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const inner = findNode(n.children, id);
    if (inner) return inner;
  }
  return null;
}

export default function CategoryPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [tree, setTree] = useState<CategoryNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"create" | "edit">("create");
  const [modalParentId, setModalParentId] = useState<string | null>(null);
  const [form] = Form.useForm<FormValues>();

  const fetchTree = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCategoriesTree();
      setTree(data);
      // 첫 로드 시 모든 1depth 펼침
      setExpandedKeys(data.map((n) => n.id));
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "카테고리 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      await fetchTree();
    };
    void run();
  }, [fetchTree]);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    return findNode(tree, selectedId);
  }, [tree, selectedId]);

  const openCreate = (parentId: string | null) => {
    setModalMode("create");
    setModalParentId(parentId);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (node: CategoryNode) => {
    setModalMode("edit");
    setModalParentId(node.parent_id ?? null);
    form.setFieldsValue({
      name: node.name,
      code: node.code ?? undefined,
      color: node.color ?? undefined,
    });
    setSelectedId(node.id);
    setModalOpen(true);
  };

  const handleSubmit = async (values: FormValues) => {
    try {
      if (modalMode === "create") {
        const body: CategoryCreate = {
          name: values.name,
          code: values.code || null,
          color: values.color || null,
          parent_id: modalParentId,
        };
        await createCategory(body);
        message.success("추가되었습니다");
      } else if (selected) {
        const body: CategoryUpdate = {
          name: values.name,
          code: values.code || null,
          color: values.color || null,
        };
        await updateCategory(selected.id, body);
        message.success("수정되었습니다");
      }
      setModalOpen(false);
      await fetchTree();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "저장 실패"));
    }
  };

  const handleDelete = async (node: CategoryNode) => {
    try {
      await deleteCategory(node.id);
      message.success("삭제되었습니다");
      if (selectedId === node.id) setSelectedId(null);
      await fetchTree();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "삭제 실패 (자식 카테고리가 있으면 삭제 불가)"));
    }
  };

  const treeData = useMemo(() => toTreeData(tree), [tree]);

  // 현재 선택 노드의 깊이
  const selectedDepth = useMemo(() => {
    if (!selected) return 0;
    return nodeDepth(selected, tree);
  }, [selected, tree]);

  const canAddChild = (depth: number) => depth < 3;

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          카테고리 관리
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          거래 카테고리(계정과목) 트리 · 최대 depth 3
          {!isAdmin && <Text type="warning"> · 보기 전용 (관리자만 편집 가능)</Text>}
        </Paragraph>
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "1fr 1fr" }}>
        <Card
          size="small"
          title="카테고리 트리"
          extra={
            <Space size={4}>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => void fetchTree()}
              >
                새로고침
              </Button>
              {isAdmin && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => openCreate(null)}
                >
                  최상위 추가
                </Button>
              )}
            </Space>
          }
        >
          {tree.length === 0 && !loading ? (
            <Empty description="카테고리가 없습니다" />
          ) : (
            <Tree
              treeData={treeData}
              selectedKeys={selectedId ? [selectedId] : []}
              expandedKeys={expandedKeys}
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={(keys) => setSelectedId((keys[0] as string) ?? null)}
              showLine
            />
          )}
        </Card>

        <Card size="small" title={selected ? `상세 — ${selected.name}` : "노드를 선택하세요"}>
          {!selected ? (
            <Empty description="좌측 트리에서 카테고리를 선택하세요" />
          ) : (
            <div>
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                <Text>
                  <Text type="secondary">이름: </Text>
                  {selected.name}
                </Text>
                <Text>
                  <Text type="secondary">코드: </Text>
                  {selected.code || "-"}
                </Text>
                <Text>
                  <Text type="secondary">색상: </Text>
                  {selected.color ? (
                    <Space size={4}>
                      <span
                        style={{
                          display: "inline-block",
                          width: 14,
                          height: 14,
                          borderRadius: 3,
                          background: selected.color,
                          verticalAlign: "middle",
                        }}
                      />
                      <Text style={{ fontFamily: "monospace" }}>{selected.color}</Text>
                    </Space>
                  ) : (
                    "-"
                  )}
                </Text>
                <Text>
                  <Text type="secondary">깊이: </Text>
                  {selectedDepth}
                </Text>
                <Text>
                  <Text type="secondary">자식 수: </Text>
                  {selected.children.length}
                </Text>
              </Space>

              {isAdmin && (
                <>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginTop: 16, fontSize: 12 }}
                    message="자식이 있는 카테고리는 삭제할 수 없습니다. 먼저 자식을 정리하세요."
                  />
                  <Space style={{ marginTop: 12 }}>
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => openEdit(selected)}
                    >
                      편집
                    </Button>
                    {canAddChild(selectedDepth) && (
                      <Button
                        icon={<PlusOutlined />}
                        onClick={() => openCreate(selected.id)}
                      >
                        하위 추가
                      </Button>
                    )}
                    <Popconfirm
                      title="이 카테고리를 삭제할까요?"
                      okText="삭제"
                      cancelText="취소"
                      onConfirm={() => handleDelete(selected)}
                    >
                      <Button danger icon={<DeleteOutlined />}>
                        삭제
                      </Button>
                    </Popconfirm>
                  </Space>
                </>
              )}
            </div>
          )}
        </Card>
      </div>

      <Modal
        title={modalMode === "create" ? "카테고리 추가" : "카테고리 편집"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          {modalMode === "create" && modalParentId && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={`상위: ${findNode(tree, modalParentId)?.name ?? modalParentId}`}
            />
          )}
          <Form.Item
            name="name"
            label="이름"
            rules={[{ required: true, message: "이름을 입력하세요" }]}
          >
            <Input placeholder="예: 매출 · 식대 · 사무용품" />
          </Form.Item>
          <Form.Item name="code" label="코드 (선택)">
            <Input placeholder="회계 코드 등" />
          </Form.Item>
          <Form.Item name="color" label="색상 (선택)" getValueFromEvent={(c) => {
            if (typeof c === "string") return c;
            if (c?.toHexString) return c.toHexString();
            return undefined;
          }}>
            <ColorPicker showText format="hex" />
          </Form.Item>
        </Form>
      </Modal>

    </div>
  );
}
