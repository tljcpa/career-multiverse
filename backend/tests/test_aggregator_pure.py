"""纯函数 pytest：验证 aggregator monotonic_step / clip 边界 / counterfactual 应用。
不依赖 LLM / 不依赖外部 API，可在 CI 里离线跑。
"""
from __future__ import annotations

import pytest

from app.api.aggregator import (
    aggregate_outcomes,
    apply_counterfactual_estimate,
    _empty_aggregate,
)
from app.simulation.outcome import CompanyJourney, SimOutcome


def _mk_outcome(sim_id: str, settled: bool, salary: float = 50.0) -> SimOutcome:
    return SimOutcome(
        sim_id=sim_id,
        total_applications=10,
        total_interviews=5,
        total_offers=2 if settled else 0,
        final_destination_company="焰火" if settled else "",
        final_destination_role="算法工程师" if settled else "",
        final_salary_wan=salary if settled else 0.0,
        final_week_when_settled=8 if settled else -1,
        journeys=[
            CompanyJourney(
                company_code="焰火",
                job_title="算法工程师",
                final_stage="accepted" if settled else "rejected",
                applied_week=2,
                final_round=3 if settled else 0,
                interview_scores=[80, 75, 82] if settled else [],
                offer_salary_wan=salary if settled else 0.0,
                is_final_destination=settled,
            )
        ],
    )


class TestAggregator:
    def test_empty_outcomes_returns_empty_aggregate(self):
        agg = aggregate_outcomes("test", outcomes=[], target_n=1000)
        assert agg.label == "test"
        assert agg.n_runs == 1000
        assert agg.offer_rate == 0.0
        assert agg.settled_rate == 0.0
        assert agg.destination_distribution == {}

    def test_all_settled_offer_rate_jeffreys(self):
        # 3 次真 sim 全胜：offer_rate / settled_rate 用 Jeffreys 后验均值而非裸 100%。
        # (successes + 0.5) / (n + 1) = (3+0.5)/(3+1) = 0.875——小样本下不给绝对 100%，
        # 高但承认不确定性，避免"哪有 100% offer 率"被评委挑刺。
        outcomes = [_mk_outcome(f"s{i}", settled=True, salary=50.0) for i in range(3)]
        agg = aggregate_outcomes("all_settled", outcomes, target_n=1000)
        assert agg.offer_rate == 0.875
        assert agg.settled_rate == 0.875

    def test_no_one_settled_jeffreys_floor(self):
        # 3 次全败：settled_rate = (0+0.5)/(3+1) = 0.125，非 0——承认黑天鹅、避免绝对化。
        outcomes = [_mk_outcome(f"f{i}", settled=False) for i in range(3)]
        agg = aggregate_outcomes("none_settled", outcomes, target_n=1000)
        assert agg.settled_rate == 0.125
        # destination_distribution 应该全是"未签约"
        assert "未签约" in agg.destination_distribution
        assert agg.destination_distribution["未签约"] > 0

    def test_jeffreys_converges_to_point_estimate_large_n(self):
        # 大样本下 Jeffreys 后验应收敛到裸点估计：50 全胜 → (50+0.5)/(50+1) ≈ 0.990。
        # 验证"样本越大不确定性越小"这个统计性质，而不是永远压低。
        outcomes = [_mk_outcome(f"s{i}", settled=True, salary=50.0) for i in range(50)]
        agg = aggregate_outcomes("many_settled", outcomes, target_n=1000)
        assert agg.offer_rate > 0.98


class TestCounterfactualMonotonicStep:
    """反事实 monotonic_step：delta > 0 必不减 / delta < 0 必不增"""

    def _base(self):
        outcomes = [_mk_outcome(f"s{i}", settled=True, salary=50.0) for i in range(3)]
        return aggregate_outcomes("baseline", outcomes, target_n=1000)

    def test_positive_delta_never_decreases_offer_rate(self):
        base = self._base()
        bumped = apply_counterfactual_estimate(base, "project_strength", 30, "项目+30")
        assert bumped.offer_rate >= base.offer_rate
        assert bumped.mean_offers >= base.mean_offers
        assert bumped.settled_rate >= base.settled_rate

    def test_negative_delta_never_increases_offer_rate(self):
        base = self._base()
        dropped = apply_counterfactual_estimate(base, "project_strength", -30, "项目-30")
        assert dropped.offer_rate <= base.offer_rate
        assert dropped.mean_offers <= base.mean_offers

    def test_salary_clamp_upper_bound(self):
        base = self._base()
        bumped = apply_counterfactual_estimate(base, "project_strength", 200, "项目+200")
        # mean_salary_when_settled 上限 120
        assert bumped.mean_salary_when_settled <= 120.0

    def test_salary_clamp_lower_bound(self):
        base = self._base()
        dropped = apply_counterfactual_estimate(base, "project_strength", -200, "项目-200")
        assert dropped.mean_salary_when_settled >= 15.0

    def test_offer_rate_clamp_upper_bound(self):
        base = self._base()
        bumped = apply_counterfactual_estimate(base, "project_strength", 200, "项目+200")
        assert bumped.offer_rate <= 1.0

    def test_unknown_mutation_key_falls_back_to_default(self):
        """未知 key 应该走 default sensitivity（resume_quality），不抛异常"""
        base = self._base()
        # 不应 raise
        result = apply_counterfactual_estimate(base, "unknown_key_xyz", 10, "test")
        assert result.label == "test"


class TestEmptyAggregateFallback:
    def test_empty_aggregate_structure(self):
        agg = _empty_aggregate("empty", target_n=1000)
        assert agg.n_runs == 1000
        assert agg.offer_rate == 0.0
        assert agg.mean_salary_when_settled == 0.0
        assert agg.destination_distribution == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
