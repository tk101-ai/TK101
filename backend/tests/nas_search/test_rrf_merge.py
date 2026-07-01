"""bridge RRF 병합·자체문서 부스트 단위 테스트 (다국어 검색 회귀 방지).

순수 함수(_rrf_merge, _boost_self_company_rrf)만 검증한다 — 임베딩/Qdrant 불필요.
언어별 결과 리스트를 순위기반으로 합쳐 언어 균형이 맞는지, 여러 리스트에 나온
청크가 상위로 올라오는지, 자체문서 부스트가 순위를 끌어올리는지를 본다.
"""
from __future__ import annotations

from unittest.mock import patch

from app.services.nas_search import bridge
from app.services.nas_search.bridge import (
    NasChunkHit,
    _boost_self_company_rrf,
    _rrf_merge,
)


def _hit(cid: str, path: str = "", score: float = 0.0) -> NasChunkHit:
    return NasChunkHit(
        chunk_id=cid,
        file_id=cid,
        file_path=path,
        file_name=path or None,
        chunk_index=0,
        content=f"content-{cid}",
        score=score,
    )


class TestRrfMerge:
    def test_score_scale_ignored_uses_rank(self) -> None:
        # KO 리스트는 cosine 0.6대, ZH 리스트는 0.9대라도 각 리스트 1위는 동점이어야
        # 한다(순위기반). k=60 → 1위 기여 = 1/61.
        ko = [_hit("k1", score=0.61), _hit("k2", score=0.60)]
        zh = [_hit("z1", score=0.95), _hit("z2", score=0.94)]
        merged = _rrf_merge([ko, zh], k=60)
        top_ids = {merged[0].chunk_id, merged[1].chunk_id}
        assert top_ids == {"k1", "z1"}  # 각 언어 1위가 공동 최상위
        assert abs(merged[0].score - 1.0 / 61) < 1e-9

    def test_cross_list_agreement_boosts(self) -> None:
        # 두 언어 풀에 모두 나온 청크는 RRF 가 합산돼 단일 리스트 1위보다 위로.
        ko = [_hit("shared"), _hit("k2")]
        zh = [_hit("z1"), _hit("shared")]
        merged = _rrf_merge([ko, zh], k=60)
        assert merged[0].chunk_id == "shared"
        # shared = 1/61 + 1/62 > 단독 1위 1/61
        assert merged[0].score > 1.0 / 61

    def test_dedupes_by_chunk_id_keeping_first_repr(self) -> None:
        ko = [_hit("shared", path="/a.pptx")]
        zh = [_hit("shared", path="/b.pptx")]
        merged = _rrf_merge([ko, zh], k=60)
        assert len(merged) == 1
        assert merged[0].file_path == "/a.pptx"  # 처음 본 대표 hit 유지

    def test_single_list_preserves_rank_order(self) -> None:
        ko = [_hit("k1"), _hit("k2"), _hit("k3")]
        merged = _rrf_merge([ko], k=60)
        assert [h.chunk_id for h in merged] == ["k1", "k2", "k3"]


class TestBoostSelfCompanyRrf:
    def test_marker_path_gets_promoted(self) -> None:
        # 자체문서(마커 포함)는 1/(k+1) 가산으로 비슷한 순위대에서 앞선다.
        hits = [
            _hit("a", path="/mnt/nas/MARKETING/x.pptx", score=1.0 / 61),
            _hit("b", path="/mnt/nas/COMPANY/회사소개.pptx", score=1.0 / 62),
        ]
        with patch.object(bridge.settings, "nas_self_company_boost", 0.06), patch.object(
            bridge.settings, "nas_self_company_path_marker", "/COMPANY/"
        ):
            out = _boost_self_company_rrf(hits, k=60)
        assert out[0].chunk_id == "b"  # 부스트로 역전

    def test_disabled_when_boost_zero(self) -> None:
        hits = [_hit("a", path="/mnt/nas/COMPANY/x.pptx", score=0.1)]
        with patch.object(bridge.settings, "nas_self_company_boost", 0.0):
            out = _boost_self_company_rrf(hits, k=60)
        assert out[0].score == 0.1  # 가산 없음
