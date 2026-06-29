import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Input,
  List,
  message,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { UploadFile } from "antd";
import {
  AuditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  deleteDocgenDocument,
  downloadGeneratedDocx,
  downloadGeneratedPptx,
  generateDocument,
  getDocgenDocument,
  listDocgenDocuments,
  listRetouchPresets,
  listSharedRetouchPresets,
  presetTheme,
  regenerateSection,
  reviewDocument,
  type DocgenDocumentBrief,
  type RetouchPreset,
  type SharedRetouchPreset,
  type DocGenResponse,
  type DocReviewResponse,
  type DocSection,
  type DocSectionReview,
  type DocType,
  type SourceMode,
} from "../../api/docgen";
import RetouchPromptPanel from "../../components/forms/RetouchPromptPanel";
import DocCreateWizard, {
  toneDirective,
  type WizardFreePayload,
} from "../../components/forms/DocCreateWizard";

const SEARCH_DEBOUNCE_MS = 200;

const { Text } = Typography;
const DOC_TYPES: DocType[] = ["제안서", "계획서", "보고서", "일반"];
const SOURCE_OPTIONS: { label: string; value: SourceMode }[] = [
  { label: "NAS 자료(RAG)", value: "rag" },
  { label: "업로드 문서", value: "uploaded" },
  { label: "둘 다", value: "both" },
];
// 품질 모드 — 초안(빠름) / 고품질(검수). value 는 highQuality 불리언에 매핑.
const QUALITY_OPTIONS: { label: string; value: "draft" | "high" }[] = [
  { label: "초안(빠름)", value: "draft" },
  { label: "고품질(검수)", value: "high" },
];
const UPLOAD_ACCEPT = ".pdf,.docx,.xlsx,.csv,.txt,.pptx";
const MAX_UPLOAD_FILES = 5;

/**
 * 요구 기반 문서 생성 (T5 확장).
 * 주제 → NAS RAG → Claude 초안 → 인라인 편집/섹션 재생성 → docx/PPT 다운로드.
 */
export default function DocGenPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [topic, setTopic] = useState("");
  const [docType, setDocType] = useState<DocType>("제안서");
  const [sourceMode, setSourceMode] = useState<SourceMode>("rag");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocGenResponse | null>(null);
  // 품질 모드: false=초안(빠름), true=고품질(LLM 검수→재생성 루프). 기본=초안.
  const [highQuality, setHighQuality] = useState(false);
  // 장시간 작업 경과 초(setInterval 로 1초마다 증가). 오버레이에 라이브 표시.
  const [elapsed, setElapsed] = useState(0);

  // 업로드된 실제 File 객체들 — 생성·재생성·검수 핸들러가 공유한다(무상태 멀티파트 재전송).
  const files = fileList
    .map((f) => f.originFileObj as File | undefined)
    .filter((f): f is File => !!f);
  const showUpload = sourceMode !== "rag";

  // 생성 결과를 편집 가능한 상태로 보관(다운로드·재생성은 이 상태 기준).
  const [title, setTitle] = useState("");
  const [sections, setSections] = useState<DocSection[]>([]);

  // ── 문서 작성 마법사 + 톤/포맷 ──
  const [wizardOpen, setWizardOpen] = useState(false);
  const [tone, setTone] = useState<string | undefined>();
  const [preferredFormat, setPreferredFormat] = useState<
    "docx" | "pptx" | undefined
  >();

  // ── 디자인 프리셋(리터치 프롬프트) — 생성 전에 골라 첫 생성부터 적용 ──
  const [myPresets, setMyPresets] = useState<RetouchPreset[]>([]);
  const [sharedPresets, setSharedPresets] = useState<SharedRetouchPreset[]>([]);
  const [designPresetId, setDesignPresetId] = useState<string | undefined>();

  // 프리셋 목록 로드(내 것 + 공유). 드롭다운 열 때마다 최신화(패널에서 새로 저장했을 수 있음).
  const reloadPresets = async () => {
    try {
      const [mine, shared] = await Promise.all([
        listRetouchPresets(),
        listSharedRetouchPresets(),
      ]);
      setMyPresets(mine);
      setSharedPresets(shared);
    } catch {
      // 프리셋 로드 실패해도 생성은 가능 — 조용히 무시.
    }
  };
  useEffect(() => {
    void reloadPresets();
  }, []);

  // 톤 + 선택 프리셋을 합성한 design_directive(생성 시 주입).
  const designDirective = useMemo(() => {
    const presetText = designPresetId
      ? (myPresets.find((p) => p.id === designPresetId)?.prompt_text ??
        sharedPresets.find((p) => p.id === designPresetId)?.prompt_text)
      : undefined;
    return (
      [toneDirective(tone), presetText].filter(Boolean).join("\n\n") || undefined
    );
  }, [designPresetId, tone, myPresets, sharedPresets]);

  // 셀렉트 옵션 — 내 프리셋 / 공유 프리셋 그룹(중복 제거: 공유 목록의 내 것은 제외).
  const presetOptions = useMemo(
    () => [
      {
        label: "내 프리셋",
        options: myPresets.map((p) => ({
          label: `${p.title} · ${p.target}`,
          value: p.id,
        })),
      },
      {
        label: "공유 프리셋",
        options: sharedPresets
          .filter((p) => !p.is_mine)
          .map((p) => ({
            label: `${p.title} · ${p.owner_name ?? "?"}`,
            value: p.id,
          })),
      },
    ],
    [myPresets, sharedPresets],
  );

  // ?wizard=1 로 진입하면 마법사 자동 오픈(허브/사이드바에서 유도). 1회 처리 후 파라미터 정리.
  useEffect(() => {
    if (searchParams.get("wizard") === "1") {
      setWizardOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete("wizard");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // ── 내 문서(저장된 생성 결과) 목록/검색 상태 ──
  const [docs, setDocs] = useState<DocgenDocumentBrief[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docSearchInput, setDocSearchInput] = useState("");
  const [docQuery, setDocQuery] = useState("");
  // 현재 결과 뷰가 어느 저장 문서에서 왔는지(목록 하이라이트용). 새 생성/없음이면 null.
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  // 생성/삭제 후 목록 재조회 트리거.
  const [docsRefreshKey, setDocsRefreshKey] = useState(0);

  // 검색어 debounce.
  const docSearchRef = useRef<number | null>(null);
  useEffect(() => {
    if (docSearchRef.current !== null) {
      window.clearTimeout(docSearchRef.current);
    }
    docSearchRef.current = window.setTimeout(() => {
      setDocQuery(docSearchInput);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (docSearchRef.current !== null) {
        window.clearTimeout(docSearchRef.current);
      }
    };
  }, [docSearchInput]);

  // 내 문서 목록 조회(검색어/새로고침 키 변경 시).
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setDocsLoading(true);
      try {
        const q = docQuery.trim();
        const data = await listDocgenDocuments(q.length > 0 ? q : undefined);
        if (!cancelled) setDocs(data);
      } catch {
        if (!cancelled) setDocs([]);
      } finally {
        if (!cancelled) setDocsLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [docQuery, docsRefreshKey]);

  // 라이브러리 등에서 ?doc=<id> 로 진입하면 해당 저장 문서를 자동으로 불러온다(딥링크 재열람).
  // 한 번 처리한 뒤에는 URL 에서 doc 파라미터를 제거해 새로고침 시 중복 로드를 막는다.
  const deepLinkHandledRef = useRef<string | null>(null);
  useEffect(() => {
    const docId = searchParams.get("doc");
    if (!docId || deepLinkHandledRef.current === docId) return;
    deepLinkHandledRef.current = docId;
    let cancelled = false;
    const run = async () => {
      setBusy(true);
      try {
        const doc = await getDocgenDocument(docId);
        if (cancelled) return;
        setResult({
          title: doc.title,
          sections: doc.sections,
          markdown: "",
          sources: doc.sources,
          model: "",
        });
        setTitle(doc.title);
        setSections(doc.sections);
        setFeedbacks({});
        setReview(null);
        setActiveDocId(doc.id);
        if (doc.topic) setTopic(doc.topic);
        if (doc.doc_type) setDocType(doc.doc_type);
        if (doc.source_mode) setSourceMode(doc.source_mode);
      } catch (e) {
        if (!cancelled) {
          message.error((e as any)?.response?.data?.detail || "문서 불러오기 실패");
        }
      } finally {
        if (!cancelled) setBusy(false);
        // URL 정리(다른 파라미터는 보존).
        const next = new URLSearchParams(searchParams);
        next.delete("doc");
        setSearchParams(next, { replace: true });
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({});
  const [regenIdx, setRegenIdx] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState<DocReviewResponse | null>(null);
  // 검수 이슈 기반 자동 보강(원클릭) 진행 상태.
  const [autoFixHeading, setAutoFixHeading] = useState<string | null>(null);
  const [autoFixingAll, setAutoFixingAll] = useState(false);
  // 순차 보강 진행률(전체 보강 오버레이 tip 표시용).
  const [autoFixProgress, setAutoFixProgress] = useState<{ done: number; total: number }>({
    done: 0,
    total: 0,
  });

  // 장시간 LLM 작업 동안 경과 초를 1초마다 증가시킨다(로딩 시작 시 0으로 리셋,
  // 끝나면 인터벌 정리). busy/reviewing/autoFixingAll 중 하나라도 켜지면 동작.
  const loading = busy || reviewing || autoFixingAll;
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (loading) {
      setElapsed(0);
      const startedAt = Date.now();
      intervalRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startedAt) / 1000));
      }, 1000);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [loading]);

  const handleGenerate = async () => {
    const t = topic.trim();
    if (t.length < 2) {
      message.warning("작성 요구/주제를 입력하세요");
      return;
    }
    if (sourceMode === "uploaded" && files.length === 0) {
      message.warning("업로드 문서를 1개 이상 추가하거나 출처를 바꾸세요");
      return;
    }
    setBusy(true);
    try {
      const res = await generateDocument({
        topic: t,
        doc_type: docType,
        source_mode: sourceMode,
        auto_review: highQuality,
        design_directive: designDirective,
        files,
      });
      setResult(res);
      setTitle(res.title);
      setSections(res.sections);
      setFeedbacks({});
      setReview(null);
      // 방금 저장된 문서 id 로 목록 하이라이트 + 목록 갱신.
      setActiveDocId(res.document_id ?? null);
      setDocsRefreshKey((k) => k + 1);
      message.success(
        designDirective
          ? `초안 생성 완료 (프리셋 적용 · 참고 ${res.sources.length}건)`
          : `초안 생성 완료 (참고 ${res.sources.length}건)`,
      );
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 생성 실패");
    } finally {
      setBusy(false);
    }
  };

  // 마법사 완료(자유 작성) — 수집값으로 바로 생성. state 도 채워 컨트롤을 동기화.
  // 화면 전체 비우기 — 빈 상태에서 새로 시작(이전 내용 잔존 방지).
  const clearAll = () => {
    setResult(null);
    setSections([]);
    setTitle("");
    setTopic("");
    setActiveDocId(null);
    setReview(null);
    setFeedbacks({});
    setDesignPresetId(undefined);
    setTone(undefined);
    setPreferredFormat(undefined);
    setFileList([]);
  };

  const handleWizardGenerate = async (p: WizardFreePayload) => {
    // 마법사 = 새 문서. 이전 결과/내용을 먼저 비워 잔존 방지(빈 화면에서 시작).
    setResult(null);
    setSections([]);
    setTitle("");
    setActiveDocId(null);
    setReview(null);
    setFeedbacks({});

    setDocType(p.docType);
    setSourceMode(p.sourceMode);
    setFileList(p.fileList);
    setHighQuality(p.highQuality);
    setDesignPresetId(p.designPresetId);
    setTone(p.tone);
    setPreferredFormat(p.preferredFormat);
    setTopic(p.topic);

    // 마법사가 해석해 넘긴 directive 를 그대로 사용(전달 신뢰성).
    const directive = p.designDirective;
    const wizardFiles = p.fileList
      .map((f) => f.originFileObj as File | undefined)
      .filter((f): f is File => !!f);

    setBusy(true);
    try {
      const res = await generateDocument({
        topic: p.topic,
        doc_type: p.docType,
        source_mode: p.sourceMode,
        auto_review: p.highQuality,
        design_directive: directive,
        files: wizardFiles,
      });
      setResult(res);
      setTitle(res.title);
      setSections(res.sections);
      setFeedbacks({});
      setReview(null);
      setActiveDocId(res.document_id ?? null);
      setDocsRefreshKey((k) => k + 1);
      const fmt = p.preferredFormat === "pptx" ? "PPT" : "Word";
      message.success(
        `${fmt} 문서 생성 완료${directive ? " · 프롬프트 적용" : ""} (참고 ${res.sources.length}건)`,
      );
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 생성 실패");
    } finally {
      setBusy(false);
    }
  };

  // 리터치 프롬프트를 디자인 지시문으로 먹여 문서를 다시 생성(내부 재생성).
  const handleRetouchRegenerate = async (directive: string) => {
    const t = topic.trim();
    if (t.length < 2) {
      message.warning("재생성하려면 주제가 필요합니다");
      return;
    }
    setBusy(true);
    try {
      const res = await generateDocument({
        topic: t,
        doc_type: docType,
        source_mode: sourceMode,
        auto_review: highQuality,
        design_directive: directive,
        files,
      });
      setResult(res);
      setTitle(res.title);
      setSections(res.sections);
      setFeedbacks({});
      setReview(null);
      setActiveDocId(res.document_id ?? null);
      setDocsRefreshKey((k) => k + 1);
      message.success("리터치 프롬프트로 재생성했습니다");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "재생성 실패");
    } finally {
      setBusy(false);
    }
  };

  // 저장된 문서를 현재 결과 뷰로 불러온다(재열람 — 재렌더/다운로드/출처 확인).
  const handleOpenDoc = async (id: string) => {
    setBusy(true);
    try {
      const doc = await getDocgenDocument(id);
      // 결과 뷰 복원: result 는 sources 표시에만 쓰이므로 최소 형태로 채운다.
      setResult({
        title: doc.title,
        sections: doc.sections,
        markdown: "",
        sources: doc.sources,
        model: "",
      });
      setTitle(doc.title);
      setSections(doc.sections);
      setFeedbacks({});
      setReview(null);
      setActiveDocId(doc.id);
      // 저장된 문서의 주제/문서종류/출처모드를 입력 컨트롤에도 복원.
      if (doc.topic) setTopic(doc.topic);
      if (doc.doc_type) setDocType(doc.doc_type);
      if (doc.source_mode) setSourceMode(doc.source_mode);
      message.success("저장된 문서를 불러왔습니다");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 불러오기 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteDoc = async (id: string) => {
    try {
      await deleteDocgenDocument(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
      if (activeDocId === id) setActiveDocId(null);
      message.success("문서를 삭제했습니다");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 삭제 실패");
    }
  };

  const updateSection = (i: number, patch: Partial<DocSection>) =>
    setSections((prev) => prev.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  const deleteSection = (i: number) =>
    setSections((prev) => prev.filter((_, idx) => idx !== i));

  const addSection = () =>
    setSections((prev) => [...prev, { heading: "새 섹션", body: "" }]);

  const handleRegenerate = async (i: number) => {
    setRegenIdx(i);
    try {
      const res = await regenerateSection({
        topic: topic.trim(),
        doc_type: docType,
        heading: sections[i].heading,
        current_body: sections[i].body,
        feedback: feedbacks[i] ?? "",
        source_mode: sourceMode,
        files,
      });
      updateSection(i, res.section);
      setFeedbacks((prev) => ({ ...prev, [i]: "" }));
      message.success("섹션 재생성 완료");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "섹션 재생성 실패");
    } finally {
      setRegenIdx(null);
    }
  };

  // 검수 결과의 issues + suggestions 를 재생성용 feedback 문자열로 합친다.
  const buildReviewFeedback = (r: DocSectionReview): string => {
    const lines = [
      ...(r.grounded ? [] : ["근거가 불충분합니다. 참고 자료에 기반해 사실을 보강하세요."]),
      ...r.issues.map((iss) => `문제: ${iss}`),
      ...r.suggestions.map((sg) => `개선: ${sg}`),
    ];
    return lines.join("\n");
  };

  // 검수 항목 heading 을 현재 섹션 배열의 인덱스로 매핑(편집으로 못 찾으면 -1).
  const findSectionIndex = (heading: string): number =>
    sections.findIndex((s) => s.heading.trim() === heading.trim());

  // 한 섹션을 검수 피드백 기준으로 재생성하고, 해당 섹션의 검수 표시는 제거(재검증 필요).
  const regenerateFromReview = async (r: DocSectionReview): Promise<boolean> => {
    const idx = findSectionIndex(r.heading);
    if (idx < 0) {
      message.warning(`"${r.heading}" 섹션을 찾지 못했습니다(제목이 바뀐 듯). 건너뜁니다.`);
      return false;
    }
    const res = await regenerateSection({
      topic: topic.trim(),
      doc_type: docType,
      heading: sections[idx].heading,
      current_body: sections[idx].body,
      feedback: buildReviewFeedback(r),
      source_mode: sourceMode,
      files,
    });
    updateSection(idx, res.section);
    // 재생성된 섹션의 검수 결과는 더 이상 유효하지 않으므로 목록에서 제거.
    setReview((prev) =>
      prev
        ? { ...prev, section_reviews: prev.section_reviews.filter((sr) => sr !== r) }
        : prev,
    );
    return true;
  };

  // 단일 섹션 "이 이슈 반영해 재생성".
  const handleAutoFixSection = async (r: DocSectionReview) => {
    setAutoFixHeading(r.heading);
    try {
      const ok = await regenerateFromReview(r);
      if (ok) message.success(`"${r.heading}" 이슈 반영 재생성 완료`);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "이슈 반영 재생성 실패");
    } finally {
      setAutoFixHeading(null);
    }
  };

  // "지적된 섹션 모두 자동 보강" — 이슈 있는 섹션들을 순차 재생성.
  const handleAutoFixAll = async () => {
    if (!review) return;
    const targets = review.section_reviews.filter((r) => !r.grounded || r.issues.length > 0);
    if (targets.length === 0) return;
    setAutoFixingAll(true);
    setAutoFixProgress({ done: 0, total: targets.length });
    let done = 0;
    let skipped = 0;
    try {
      for (const r of targets) {
        try {
          const ok = await regenerateFromReview(r);
          if (ok) done += 1;
          else skipped += 1;
        } catch {
          skipped += 1;
        }
        setAutoFixProgress((prev) => ({ ...prev, done: prev.done + 1 }));
      }
      message.success(
        `자동 보강 완료 — ${done}개 재생성${skipped > 0 ? `, ${skipped}개 건너뜀` : ""}`,
      );
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "자동 보강 실패");
    } finally {
      setAutoFixingAll(false);
      setAutoFixProgress({ done: 0, total: 0 });
    }
  };

  const download = async (kind: "docx" | "pptx") => {
    if (sections.length === 0) return;
    try {
      const fn = kind === "docx" ? downloadGeneratedDocx : downloadGeneratedPptx;
      // 선택한 디자인 프리셋의 테마(색·폰트)를 편집가능 문서에 적용.
      const preset =
        myPresets.find((p) => p.id === designPresetId) ??
        sharedPresets.find((p) => p.id === designPresetId);
      await fn(title || "문서", sections, preset ? presetTheme(preset) : undefined);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || `${kind} 다운로드 실패`);
    }
  };

  const handleReview = async () => {
    if (sections.length === 0) return;
    setReviewing(true);
    try {
      const res = await reviewDocument({
        topic: topic.trim(),
        doc_type: docType,
        title: title || "문서",
        sections,
        source_mode: sourceMode,
        files,
      });
      setReview(res);
      message.success(`품질 검증 완료 — 점수 ${res.overall_score}/100`);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "품질 검증 실패");
    } finally {
      setReviewing(false);
    }
  };

  // 장시간 LLM 작업용 전체화면 차단 오버레이 tip(작업별 안내 + 경과 초 라이브).
  const elapsedLabel = `${elapsed}초 경과`;
  let overlayTip: string;
  if (autoFixingAll) {
    overlayTip = `${autoFixProgress.done}/${autoFixProgress.total} 섹션 보강 중 · ${elapsedLabel}`;
  } else if (busy) {
    overlayTip = highQuality
      ? `AI가 문서를 작성·검수하고 있습니다 · ${elapsedLabel} (보통 1~2분, 자료가 많으면 더 걸릴 수 있어요)`
      : `AI가 문서를 작성하고 있습니다 · ${elapsedLabel} (보통 30초 내외, 자료가 많으면 더 걸릴 수 있어요)`;
  } else {
    overlayTip = `AI가 문서를 검증하고 있습니다 · ${elapsedLabel} (보통 30초 내외)`;
  }

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <Spin spinning={loading} fullscreen tip={overlayTip} />

      {/* 좌측: 내 문서(저장된 생성 결과) 목록 */}
      <div
        style={{
          width: 260,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          position: "sticky",
          top: 0,
          maxHeight: "calc(100vh - 32px)",
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "-0.01em",
          }}
        >
          내 문서{" "}
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>
            ({docs.length})
          </Text>
        </div>
        <Input
          size="small"
          prefix={<SearchOutlined style={{ color: "rgba(0,0,0,0.35)" }} />}
          placeholder="제목/주제 검색"
          value={docSearchInput}
          onChange={(e) => setDocSearchInput(e.target.value)}
          allowClear
        />
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          <List
            size="small"
            loading={docsLoading}
            dataSource={docs}
            locale={{ emptyText: "저장된 문서가 없습니다" }}
            renderItem={(d) => {
              const isActive = d.id === activeDocId;
              return (
                <List.Item
                  style={{
                    padding: "6px 8px",
                    borderRadius: 6,
                    background: isActive
                      ? "rgba(24,144,255,0.08)"
                      : "transparent",
                    cursor: "pointer",
                    border: isActive
                      ? "1px solid rgba(24,144,255,0.3)"
                      : "1px solid transparent",
                    marginBottom: 4,
                  }}
                  onClick={() => void handleOpenDoc(d.id)}
                  actions={[
                    <Popconfirm
                      key="del"
                      title="이 문서를 삭제할까요?"
                      okText="삭제"
                      cancelText="취소"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        void handleDeleteDoc(d.id);
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                      minWidth: 0,
                      flex: 1,
                    }}
                  >
                    <Text
                      style={{ fontSize: 12, fontWeight: 500 }}
                      ellipsis={{ tooltip: d.title }}
                    >
                      {d.title}
                    </Text>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      {d.doc_type && (
                        <Tag
                          style={{
                            fontSize: 10,
                            lineHeight: "16px",
                            padding: "0 4px",
                          }}
                        >
                          {d.doc_type}
                        </Tag>
                      )}
                      <Text type="secondary" style={{ fontSize: 10 }}>
                        {new Date(d.created_at).toLocaleDateString()}
                      </Text>
                    </div>
                  </div>
                </List.Item>
              );
            }}
          />
        </div>
      </div>

      {/* 우측: 생성 입력 + 결과 */}
      <div style={{ flex: 1, minWidth: 0, maxWidth: 1080 }}>
      <div
        style={{
          marginBottom: 16,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            문서 생성{" "}
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              요구 기반 · RAG 초안 · 편집/재생성
            </Text>
          </h2>
          <Text type="secondary">
            주제를 입력하면 회사 NAS 자료를 참고해 초안을 만들고, 섹션을 직접 고치거나 다시 생성할 수 있습니다.
          </Text>
        </div>
        <Space>
          {(result || topic) && (
            <Button onClick={clearAll}>새 문서(비우기)</Button>
          )}
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => setWizardOpen(true)}
          >
            문서 만들기 (가이드)
          </Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Space wrap size={[12, 8]}>
            <Segmented
              options={DOC_TYPES}
              value={docType}
              onChange={(v) => setDocType(v as DocType)}
            />
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>출처</Text>
              <Segmented
                size="small"
                options={SOURCE_OPTIONS}
                value={sourceMode}
                onChange={(v) => setSourceMode(v as SourceMode)}
              />
            </Space>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>품질</Text>
              <Segmented
                size="small"
                options={QUALITY_OPTIONS}
                value={highQuality ? "high" : "draft"}
                onChange={(v) => setHighQuality(v === "high")}
                disabled={busy}
              />
            </Space>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>디자인 프리셋</Text>
              <Select
                size="small"
                style={{ minWidth: 180 }}
                placeholder="없음"
                allowClear
                value={designPresetId}
                onChange={(v) => setDesignPresetId(v)}
                onDropdownVisibleChange={(open) => {
                  if (open) void reloadPresets();
                }}
                options={presetOptions}
                disabled={busy}
              />
            </Space>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {highQuality
              ? "고품질: 초안 작성 후 AI 검수→문제 섹션 재생성까지 돌립니다(보통 1~2분, 더 정확)."
              : "초안: 빠르게 한 번에 작성합니다(보통 30초 내외)."}
          </Text>
          {designDirective && (
            <Text type="success" style={{ fontSize: 12 }}>
              선택한 디자인 프리셋을 적용해 첫 생성부터 그 방향(레이아웃·톤)으로 작성합니다.
            </Text>
          )}
          {showUpload && (
            <Upload
              multiple
              accept={UPLOAD_ACCEPT}
              fileList={fileList}
              maxCount={MAX_UPLOAD_FILES}
              beforeUpload={() => false}
              onChange={({ fileList: fl }) => setFileList(fl.slice(0, MAX_UPLOAD_FILES))}
            >
              <Button icon={<UploadOutlined />} size="small">
                참고 문서 업로드 (최대 {MAX_UPLOAD_FILES}개 · PDF/DOCX/XLSX/CSV/TXT/PPTX)
              </Button>
            </Upload>
          )}
          <Input.TextArea
            rows={4}
            placeholder="예: 신세계백화점 대상 중국 SNS 운영 대행 제안서를 작성해줘. 운영 채널과 견적 흐름 포함."
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={busy}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={handleGenerate}
            loading={busy}
            disabled={topic.trim().length < 2}
          >
            초안 생성
          </Button>
        </Space>
      </Card>

      {result && (
        <Card
          title={
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {preferredFormat && (
                <Tag
                  color={preferredFormat === "pptx" ? "magenta" : "blue"}
                  style={{ margin: 0 }}
                >
                  {preferredFormat === "pptx" ? "PPT" : "Word"}로 생성
                </Tag>
              )}
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                variant="borderless"
                style={{ fontSize: 16, fontWeight: 600, padding: 0, flex: 1 }}
              />
            </div>
          }
          extra={
            <Space>
              <Button icon={<AuditOutlined />} loading={reviewing} onClick={handleReview}>
                품질 검증
              </Button>
              {/* 만든 포맷을 주 버튼으로, 다른 포맷은 보조로(내용은 두 포맷 공용). */}
              {preferredFormat === "docx" ? (
                <>
                  <Button
                    icon={<DownloadOutlined />}
                    type="primary"
                    onClick={() => download("docx")}
                  >
                    Word 다운로드
                  </Button>
                  <Button onClick={() => download("pptx")}>PPT로도</Button>
                </>
              ) : (
                <>
                  <Button
                    icon={<DownloadOutlined />}
                    type="primary"
                    onClick={() => download("pptx")}
                  >
                    PPT 다운로드
                  </Button>
                  <Button onClick={() => download("docx")}>Word로도</Button>
                </>
              )}
            </Space>
          }
        >
          {result.sources.length > 0 &&
            (() => {
              // 출처를 업로드/NAS 두 그룹으로 나눠 실제 파일명으로 표시한다.
              const uploaded = result.sources.filter((s) => s.source_type === "uploaded");
              const nas = result.sources.filter((s) => s.source_type !== "uploaded");
              const renderGroup = (
                label: string,
                items: typeof result.sources,
                color: string,
              ) =>
                items.length === 0 ? null : (
                  <div style={{ marginBottom: 6 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{label}: </Text>
                    {items.map((s) => (
                      <Tag
                        key={s.path}
                        color={s.cited ? color : "default"}
                        title={`${s.path}${s.cited ? " · 인용됨" : " · 검색됨(미인용)"}`}
                        style={{ marginBottom: 4 }}
                      >
                        {s.cited ? "✓ " : ""}
                        {s.name || s.path} ({s.score.toFixed(2)})
                      </Tag>
                    ))}
                  </div>
                );
              return (
                <div style={{ marginBottom: 12 }}>
                  {renderGroup("업로드한 자료", uploaded, "green")}
                  {renderGroup("NAS 참고자료", nas, "blue")}
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    ✓ = 본문에 인용된 자료. 나머지는 참고용으로 검색·주입된 자료.
                  </Text>
                </div>
              );
            })()}

          {review && (
            <Alert
              type={review.overall_score >= 70 ? "success" : review.overall_score >= 40 ? "warning" : "error"}
              style={{ marginBottom: 16 }}
              showIcon
              message={`품질 점수 ${review.overall_score}/100`}
              description={
                <div>
                  <div style={{ marginBottom: 8 }}>{review.summary}</div>
                  {review.section_reviews.some((r) => !r.grounded || r.issues.length > 0) && (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        ghost
                        icon={<SyncOutlined />}
                        loading={autoFixingAll}
                        disabled={autoFixHeading !== null}
                        onClick={handleAutoFixAll}
                        style={{ marginBottom: 8 }}
                      >
                        지적된 섹션 모두 자동 보강
                      </Button>
                      <List
                        size="small"
                        dataSource={review.section_reviews.filter((r) => !r.grounded || r.issues.length > 0)}
                        renderItem={(r) => (
                          <List.Item style={{ display: "block", paddingLeft: 0 }}>
                            <Space align="center" wrap style={{ marginBottom: 2 }}>
                              <Text strong>{r.heading}</Text>
                              {!r.grounded && <Tag color="red">근거 불충분</Tag>}
                              {findSectionIndex(r.heading) < 0 && <Tag>섹션 없음</Tag>}
                              <Button
                                size="small"
                                icon={<SyncOutlined />}
                                loading={autoFixHeading === r.heading}
                                disabled={
                                  autoFixingAll ||
                                  (autoFixHeading !== null && autoFixHeading !== r.heading) ||
                                  findSectionIndex(r.heading) < 0
                                }
                                onClick={() => handleAutoFixSection(r)}
                              >
                                이 이슈 반영해 재생성
                              </Button>
                            </Space>
                            {r.issues.map((iss, k) => (
                              <div key={k} style={{ fontSize: 12, color: "#cf1322" }}>· {iss}</div>
                            ))}
                            {r.suggestions.map((sg, k) => (
                              <div key={k} style={{ fontSize: 12, color: "#8c8c8c" }}>→ {sg}</div>
                            ))}
                          </List.Item>
                        )}
                      />
                    </>
                  )}
                  {review.missing.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>누락/보강: </Text>
                      {review.missing.map((m, k) => (
                        <Tag key={k} color="orange" style={{ marginBottom: 4 }}>{m.slice(0, 40)}</Tag>
                      ))}
                    </div>
                  )}
                </div>
              }
            />
          )}

          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            {sections.map((s, i) => (
              <div key={i} style={{ borderTop: i > 0 ? "1px solid #f0f0f0" : "none", paddingTop: i > 0 ? 12 : 0 }}>
                <Space.Compact style={{ width: "100%", marginBottom: 6 }}>
                  <Input
                    value={s.heading}
                    onChange={(e) => updateSection(i, { heading: e.target.value })}
                    style={{ fontWeight: 600 }}
                  />
                  <Popconfirm title="이 섹션을 삭제할까요?" onConfirm={() => deleteSection(i)}>
                    <Button icon={<DeleteOutlined />} danger />
                  </Popconfirm>
                </Space.Compact>
                <Input.TextArea
                  value={s.body}
                  onChange={(e) => updateSection(i, { body: e.target.value })}
                  autoSize={{ minRows: 3, maxRows: 16 }}
                  style={{ marginBottom: 6 }}
                />
                <Space.Compact style={{ width: "100%" }}>
                  <Input
                    placeholder="수정 요청(선택) — 예: 견적 표를 더 구체적으로"
                    value={feedbacks[i] ?? ""}
                    onChange={(e) => setFeedbacks((prev) => ({ ...prev, [i]: e.target.value }))}
                    onPressEnter={() => handleRegenerate(i)}
                    size="small"
                  />
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={regenIdx === i}
                    onClick={() => handleRegenerate(i)}
                  >
                    재생성
                  </Button>
                </Space.Compact>
              </div>
            ))}
          </Space>

          <Button
            type="dashed"
            icon={<PlusOutlined />}
            onClick={addSection}
            style={{ marginTop: 16 }}
            block
          >
            섹션 추가
          </Button>

          <RetouchPromptPanel
            title={title}
            sections={sections}
            docType={docType}
            topic={topic}
            sourceDocumentId={activeDocId}
            onRegenerate={handleRetouchRegenerate}
            regenerating={busy}
          />
        </Card>
      )}
      </div>

      <DocCreateWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onFreeGenerate={handleWizardGenerate}
      />
    </div>
  );
}
