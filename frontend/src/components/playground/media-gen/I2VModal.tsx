import { useEffect, useState } from "react";
import { Form, Input, InputNumber, Modal, Select, Switch } from "antd";
import type { PlaygroundMediaModelOption } from "../../../api/playground";
import { ASPECT_RATIO_OPTIONS, VIDEO_RESOLUTION_OPTIONS } from "./constants";
import type { ActiveTask, I2VFormValues } from "./types";

export default function I2VModal({
  target,
  videoModels,
  onCancel,
  onSubmit,
}: {
  target: ActiveTask | null;
  videoModels: PlaygroundMediaModelOption[];
  onCancel: () => void;
  onSubmit: (values: I2VFormValues, target: ActiveTask) => Promise<void>;
}) {
  const [form] = Form.useForm<I2VFormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (target) {
      form.setFieldsValue({
        prompt: target.prompt,
        model_key: videoModels[0]?.key ?? "",
        duration: 5,
        resolution: "720P",
        aspect_ratio: "16:9",
        audio_generation: false,
        enhance_prompt: true,
      });
    }
    // 닫힐 때 form 초기화는 destroyOnClose 가 처리.
  }, [target, videoModels, form]);

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

  // 베이스가 영상이면 v2v(영상 리터치), 이미지면 i2v(이미지→영상).
  const isVideoSource = target?.kind === "video";

  return (
    <Modal
      title={isVideoSource ? "영상 리터치 (video-to-video)" : "이 이미지로 영상 만들기"}
      open={target !== null}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={isVideoSource ? "리터치 생성" : "영상 생성"}
      cancelText="취소"
      confirmLoading={submitting}
      destroyOnClose
      width={520}
    >
      {target?.outputUrl &&
        (isVideoSource ? (
          <div style={{ marginBottom: 12, textAlign: "center" }}>
            <video
              src={target.outputUrl}
              controls
              preload="metadata"
              style={{
                maxWidth: "100%",
                maxHeight: 200,
                borderRadius: 6,
                border: "1px solid rgba(0,0,0,0.08)",
              }}
            />
          </div>
        ) : (
          <div style={{ marginBottom: 12, textAlign: "center" }}>
            <img
              src={target.outputUrl}
              alt="source"
              style={{
                maxWidth: "100%",
                maxHeight: 200,
                borderRadius: 6,
                border: "1px solid rgba(0,0,0,0.08)",
              }}
            />
          </div>
        ))}
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="prompt"
          label={isVideoSource ? "수정 지시 (영상 리터치)" : "영상 프롬프트"}
          rules={[{ required: true, message: "프롬프트를 입력하세요" }]}
        >
          <Input.TextArea
            rows={3}
            placeholder={
              isVideoSource
                ? "예: 영상 색감을 시네마틱하게, 분위기를 따뜻하게"
                : "예: 카메라가 천천히 줌인하며 캐릭터가 미소 짓는다"
            }
          />
        </Form.Item>
        <Form.Item
          name="model_key"
          label="영상 모델"
          rules={[{ required: true, message: "모델을 선택하세요" }]}
        >
          <Select
            options={videoModels.map((m) => ({
              value: m.key,
              label: m.badge ? `${m.label} (${m.badge})` : m.label,
            }))}
            placeholder={
              videoModels.length === 0 ? "모델 목록 로딩 중…" : "모델을 선택하세요"
            }
          />
        </Form.Item>
        <Form.Item name="duration" label="영상 길이 (초)">
          <InputNumber min={1} max={60} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="resolution" label="해상도">
          <Select options={VIDEO_RESOLUTION_OPTIONS} />
        </Form.Item>
        <Form.Item name="aspect_ratio" label="화면 비율">
          <Select options={ASPECT_RATIO_OPTIONS} />
        </Form.Item>
        <Form.Item name="audio_generation" label="오디오 생성" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item
          name="enhance_prompt"
          label="프롬프트 자동 보강"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}
