import { Alert, Button, Space, Select, Typography } from "antd";
import { CloudUploadOutlined, ReloadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { COMPANY_FILTER_OPTIONS } from "../../api/distribution";
import { BrandSummaryCards } from "./products/BrandSummaryCards";
import { CompanySummaryCards } from "./products/CompanySummaryCards";
import { GrandTotalCards } from "./products/GrandTotalCards";
import { ProductFilters } from "./products/ProductFilters";
import { ProductTable } from "./products/ProductTable";
import type { CompanyChoice } from "./products/types";
import { PRODUCTS_FETCH_LIMIT, useProducts } from "./products/useProducts";

const { Title, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// 페이지
// ---------------------------------------------------------------------------

/**
 * 명품재고대장 조회 페이지 (T9 Phase F-D).
 *
 * 백엔드: `GET /api/distribution/data/products`
 * - 회사 / 브랜드 / 카테고리 / 검색(제품명·코드) 필터
 * - 상단 브랜드별 요약 카드 (가시성 ↑: 브랜드명 큰 글씨 + 제품/재고/매입 수치)
 * - 페이지 사이즈 50
 */
export default function ProductsPage() {
  const {
    loading,
    capped,
    fetchData,
    company,
    setCompany,
    brandFilter,
    setBrandFilter,
    categoryFilter,
    setCategoryFilter,
    searchInput,
    setSearchInput,
    companyStats,
    grandTotal,
    brandOptions,
    categoryOptions,
    brandStats,
    filtered,
  } = useProducts();

  return (
    <div style={{ maxWidth: 1680 }}>
      <div
        style={{
          marginBottom: 24,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
            명품재고대장
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            업로드된 명품재고 전체 목록입니다. 회사를 선택하면 해당 회사 적재분만
            노출됩니다. 매주 업로드 시 전체 갱신됩니다.
          </Paragraph>
        </div>
        <Space wrap>
          <Select<CompanyChoice>
            value={company}
            onChange={(v) => setCompany(v)}
            options={COMPANY_FILTER_OPTIONS}
            style={{ width: 200 }}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            새로고침
          </Button>
          <Link to="/distribution/data/upload">
            <Button type="primary" icon={<CloudUploadOutlined />}>
              데이터 업로드
            </Button>
          </Link>
        </Space>
      </div>

      {/* 전체 총합 KPI — 현재 회사 컨텍스트 기준 */}
      <GrandTotalCards grandTotal={grandTotal} company={company} />

      {/* 회사별 비교 — 항상 4 회사 노출 (회사 Select와 무관) */}
      <CompanySummaryCards
        companyStats={companyStats}
        company={company}
        onSelectCompany={setCompany}
      />

      {/* 브랜드별 요약 카드 — 현재 회사 컨텍스트 기준 */}
      <BrandSummaryCards brandStats={brandStats} company={company} />

      {capped && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`최대 ${PRODUCTS_FETCH_LIMIT.toLocaleString("ko-KR")}건만 표시 중입니다. 일부 데이터가 누락됐을 수 있어 회사/브랜드 필터로 좁혀 조회하세요.`}
        />
      )}

      <ProductFilters
        searchInput={searchInput}
        onSearchChange={setSearchInput}
        brandFilter={brandFilter}
        onBrandChange={setBrandFilter}
        brandOptions={brandOptions}
        categoryFilter={categoryFilter}
        onCategoryChange={setCategoryFilter}
        categoryOptions={categoryOptions}
      />

      <ProductTable data={filtered} loading={loading} />
    </div>
  );
}
