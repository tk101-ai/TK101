import { useEffect, useState } from "react";
import { Form, Input, Modal, Select, Switch, Typography } from "antd";
import type { PlaygroundMediaModelOption } from "../../../api/playground";
import { ASPECT_RATIO_OPTIONS } from "./constants";
import type { ActiveTask, ImageEditFormValues } from "./types";

const { Text } = Typography;

/**
 * 이미지 리터치/편집(i2i) 모달 — 완성된 이미지를 베이스로, 수정 지시 프롬프트대로
 * 편집된 새 이미지를 생성. target.outputUrl 이 베이스 이미지(미리보기).
 */
export default function ImageEditModal({
  target,
  imageModels,
  onCancel,
  onSubmit,
}: {
  target: ActiveTask | null;
  imageModels: PlaygroundMediaModelOption[];
  onCancel: () => void;
  onSubmit: (values: ImageEditFormValues, target: ActiveTask) => Promise<void>;
}) {
  const [form] = Form.useForm<ImageEditFormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (target) {
      // 이미지 통일성 — 원본을 만든 모델을 기본값으로(있고 목록에 존재하면).
      const originalInList = imageModels.some((m) => m.key === target.modelKey);
      form.setFieldsValue({
        prompt: "",
        model_key:
          target.modelKey && originalInList
            ? target.modelKey
            : (imageModels[0]?.key ?? ""),
        aspect_ratio: "1:1",
        enhance_prompt: true,
      });
    }
  }, [target, imageModels, form]);

  const handleOk = async () => {
    if (!target) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await onSubmit(values, target);
    } catch {
      // validation error — 모달 유지.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="이미지 리터치 / 수정"
      open={target !== null}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText="리터치 생성"
      cancelText="취소"
      confirmLoading={submitting}
      destroyOnClose
      width={520}
    >
      {target?.outputUrl && (
        <div style={{ marginBottom: 12, textAlign: "center" }}>
          <img
            src={target.outputUrl}
            alt="base"
            style={{
              maxWidth: "100%",
              maxHeight: 220,
              borderRadius: 6,
              border: "1px solid rgba(0,0,0,0.08)",
            }}
          />
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              이 이미지를 베이스로 아래 지시대로 수정합니다
            </Text>
          </div>
        </div>
      )}
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="prompt"
          label="수정 지시 (리터치 프롬프트)"
          rules={[{ required: true, message: "수정 내용을 입력하세요" }]}
        >
          <Input.TextArea
            rows={3}
            placeholder="예: 배경을 깔끔한 흰색 스튜디오로 바꾸고, 색감을 더 밝게"
          />
        </Form.Item>
        <Form.Item
          name="model_key"
          label="이미지 모델"
          rules={[{ required: true, message: "모델을 선택하세요" }]}
        >
          <Select
            options={imageModels.map((m) => ({
              value: m.key,
              label: m.badge ? `${m.label} (${m.badge})` : m.label,
            }))}
            placeholder={imageModels.length === 0 ? "모델 목록 로딩 중…" : "모델을 선택하세요"}
          />
        </Form.Item>
        <Form.Item name="aspect_ratio" label="화면 비율">
          <Select options={ASPECT_RATIO_OPTIONS} />
        </Form.Item>
        <Form.Item name="enhance_prompt" label="프롬프트 자동 보강" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}
