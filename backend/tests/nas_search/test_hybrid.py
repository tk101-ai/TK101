"""hybrid.py 단위 테스트 — 토큰화 / RRF 결합 / LIKE 이스케이프.

DB·임베딩 의존 없는 순수 로직만 검증. docker/CI에서 실행.
"""
from __future__ import annotations

from app.services.nas_search.hybrid import (
    like_escape,
    reciprocal_rank_fusion,
    tokenize_query,
)


class TestTokenizeQuery:
    def test_splits_on_whitespace_and_lowercases(self):
        assert tokenize_query("GUCCI 가방 면장") == ["gucci", "가방", "면장"]

    def test_preserves_dash_in_product_code(self):
        # 품번은 통째로 한 토큰이어야 ILIKE 정확 매칭이 산다.
        assert tokenize_query("12865-24-008320X") == ["12865-24-008320x"]

    def test_keeps_short_token_when_it_has_digit(self):
        # 연도 같은 숫자 토큰은 길이가 짧아도 유지.
        assert "2024" in tokenize_query("면장 2024")

    def test_drops_short_nondigit_token(self):
        # 길이 1의 비숫자 토큰은 노이즈로 제거.
        assert tokenize_query("a 가방") == ["가방"]

    def test_dedupes_preserving_order(self):
        assert tokenize_query("면장 면장 가방") == ["면장", "가방"]

    def test_strips_surrounding_quotes(self):
        assert tokenize_query('"gucci" (가방)') == ["gucci", "가방"]

    def test_respects_max_terms(self):
        q = " ".join(f"term{i}" for i in range(20))
        assert len(tokenize_query(q, max_terms=5)) == 5

    def test_empty_query_returns_empty(self):
        assert tokenize_query("") == []
        assert tokenize_query("   ") == []


class TestReciprocalRankFusion:
    def test_item_in_both_rankings_outranks_item_in_one(self):
        vector = ["a", "b", "c"]
        keyword = ["b", "d", "e"]
        scores = reciprocal_rank_fusion([vector, keyword])
        # b는 두 arm에 모두 등장 → 어느 한쪽 1위(a, b)보다 높아야 한다.
        assert scores["b"] > scores["a"]
        assert scores["b"] > scores["d"]

    def test_top_rank_scores_higher_than_lower_rank(self):
        scores = reciprocal_rank_fusion([["a", "b", "c"]])
        assert scores["a"] > scores["b"] > scores["c"]

    def test_k_constant_changes_decay(self):
        small_k = reciprocal_rank_fusion([["a", "b"]], k=1)
        large_k = reciprocal_rank_fusion([["a", "b"]], k=1000)
        # k가 작을수록 1위와 2위 점수 격차가 커진다.
        assert (small_k["a"] - small_k["b"]) > (large_k["a"] - large_k["b"])

    def test_empty_rankings(self):
        assert reciprocal_rank_fusion([]) == {}
        assert reciprocal_rank_fusion([[]]) == {}

    def test_sorted_descending_gives_fused_order(self):
        vector = ["x", "y", "z"]
        keyword = ["y", "x"]
        scores = reciprocal_rank_fusion([vector, keyword])
        order = sorted(scores, key=lambda key: scores[key], reverse=True)
        # x(1위+2위), y(2위+1위)가 z(3위, 단독)보다 앞.
        assert order[:2] == ["x", "y"] or order[:2] == ["y", "x"]
        assert order[-1] == "z"


class TestLikeEscape:
    def test_escapes_percent_and_underscore(self):
        assert like_escape("50%") == "50\\%"
        assert like_escape("a_b") == "a\\_b"

    def test_escapes_backslash_first(self):
        assert like_escape("a\\b") == "a\\\\b"

    def test_plain_text_unchanged(self):
        assert like_escape("gucci") == "gucci"
