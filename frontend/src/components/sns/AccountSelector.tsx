import { useEffect, useMemo, useState } from "react";
import { Select, message } from "antd";
import {
  getPlatformLabel,
  listAccounts,
  type Language,
  type Platform,
  type SnsAccount,
} from "../../api/sns";

/**
 * SNS 계정 라벨. 예: "유튜브 · @handle".
 * SnsPosts 의 buildAccountLabel 패턴을 공유 컴포넌트로 통일.
 */
export function buildAccountLabel(account: SnsAccount): string {
  const handle = account.handle ?? account.external_id ?? account.id.slice(0, 8);
  return `${getPlatformLabel(account.platform)} · ${handle}`;
}

interface BaseProps {
  /** 플랫폼 필터 — 지정 시 해당 플랫폼 계정만 노출. */
  filterPlatform?: Platform;
  /** 어권 필터 — 지정 시 해당 어권 계정만 노출. */
  filterLanguage?: Language;
  /** 비활성(is_active=false) 계정 포함 여부. 기본 false(활성만). */
  includeInactive?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  style?: React.CSSProperties;
  disabled?: boolean;
  /**
   * 외부에서 이미 보유한 계정 목록을 주입(선택). 주어지면 내부 fetch 생략 →
   * 부모가 react-query 등으로 캐시를 공유할 때 중복 호출 방지.
   */
  accounts?: SnsAccount[];
  /** 로드된(필터 적용 전) 계정 목록 콜백 — 부모가 카드/플랫폼 파생에 재사용. */
  onAccountsLoaded?: (accounts: SnsAccount[]) => void;
}

interface SingleProps extends BaseProps {
  mode?: "single";
  value?: string;
  onChange?: (accountId: string | undefined) => void;
}

interface MultiProps extends BaseProps {
  mode: "multi";
  value?: string[];
  onChange?: (accountIds: string[]) => void;
}

export type AccountSelectorProps = SingleProps | MultiProps;

/**
 * 동적 SNS 계정 셀렉터 (공유 컴포넌트).
 *
 * - `listAccounts()` 결과로 옵션을 구성하므로 계정 추가/삭제가 즉시 반영된다(하드코딩 없음).
 * - 단일/다중 선택, 플랫폼·어권 필터 지원.
 * - 화면마다 중복 구현하던 셀렉터를 이 컴포넌트로 대체한다.
 */
export default function AccountSelector(props: AccountSelectorProps) {
  const {
    filterPlatform,
    filterLanguage,
    includeInactive = false,
    placeholder = "계정 선택",
    allowClear = true,
    style,
    disabled,
    accounts: injectedAccounts,
    onAccountsLoaded,
  } = props;

  const isMulti = props.mode === "multi";

  const [fetched, setFetched] = useState<SnsAccount[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (injectedAccounts) {
      setFetched(injectedAccounts);
      onAccountsLoaded?.(injectedAccounts);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listAccounts()
      .then((res) => {
        if (cancelled) return;
        setFetched(res.data);
        onAccountsLoaded?.(res.data);
      })
      .catch(() => {
        if (!cancelled) message.error("계정 목록 조회 실패");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // injectedAccounts 의 참조 변경 / 마운트 시에만 재조회.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injectedAccounts]);

  const options = useMemo(() => {
    return fetched
      .filter((a) => includeInactive || a.is_active)
      .filter((a) => !filterPlatform || a.platform === filterPlatform)
      .filter((a) => !filterLanguage || a.language === filterLanguage)
      .map((a) => ({ label: buildAccountLabel(a), value: a.id }));
  }, [fetched, includeInactive, filterPlatform, filterLanguage]);

  if (isMulti) {
    const { value, onChange } = props as MultiProps;
    return (
      <Select
        mode="multiple"
        value={value}
        loading={loading}
        disabled={disabled}
        placeholder={placeholder}
        allowClear={allowClear}
        style={{ minWidth: 220, ...style }}
        options={options}
        onChange={(v) => onChange?.((v as string[]) ?? [])}
        showSearch
        optionFilterProp="label"
        maxTagCount="responsive"
      />
    );
  }

  const { value, onChange } = props as SingleProps;
  return (
    <Select
      value={value}
      loading={loading}
      disabled={disabled}
      placeholder={placeholder}
      allowClear={allowClear}
      style={{ width: 220, ...style }}
      options={options}
      onChange={(v) => onChange?.(v as string | undefined)}
      showSearch
      optionFilterProp="label"
    />
  );
}
