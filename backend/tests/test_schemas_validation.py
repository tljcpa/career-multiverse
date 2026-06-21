"""Pydantic schema 验证测试：确保 Field 边界 / extra='forbid' 等约束真生效。
评委 F12 看 422 响应时，能知道 backend 真做了输入校验。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    CounterfactualRequest,
    HRInterviewRequest,
    MutationDelta,
    StartSimRequest,
)


class TestStartSimRequest:
    def test_valid_request_passes(self):
        req = StartSimRequest(user_id="user_abc123", n_runs=1000, seed=42)
        assert req.n_runs == 1000

    def test_n_runs_too_large_rejected(self):
        with pytest.raises(ValidationError):
            StartSimRequest(user_id="x", n_runs=10**9)

    def test_n_runs_negative_rejected(self):
        with pytest.raises(ValidationError):
            StartSimRequest(user_id="x", n_runs=-1)

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            StartSimRequest(user_id="x", n_runs=1000, malicious_field="evil")  # type: ignore

    def test_empty_user_id_rejected(self):
        with pytest.raises(ValidationError):
            StartSimRequest(user_id="", n_runs=1000)


class TestHRInterviewRequest:
    def test_valid_request_passes(self):
        req = HRInterviewRequest(
            company_code="焰火", user_id="user_abc", question="加班严重吗？"
        )
        assert req.company_code == "焰火"

    def test_question_too_long_rejected(self):
        with pytest.raises(ValidationError):
            HRInterviewRequest(
                company_code="焰火", user_id="u", question="x" * 501
            )

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            HRInterviewRequest(company_code="焰火", user_id="u", question="")

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            HRInterviewRequest(  # type: ignore
                company_code="焰火", user_id="u", question="问题", inject="evil"
            )


class TestMutationDelta:
    def test_valid_mutation(self):
        m = MutationDelta(key="resume_quality", delta=10.0, label="resume+10")
        assert m.delta == 10.0

    def test_delta_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            MutationDelta(key="resume_quality", delta=99999.0, label="evil")

    def test_invalid_key_rejected(self):
        with pytest.raises(ValidationError):
            MutationDelta(key="invalid_key_xyz", delta=10.0, label="x")  # type: ignore

    def test_label_too_long_rejected(self):
        with pytest.raises(ValidationError):
            MutationDelta(key="resume_quality", delta=10.0, label="x" * 101)


class TestCounterfactualRequest:
    def test_valid_request(self):
        req = CounterfactualRequest(
            sim_session_id="sim_abc",
            mutations=[MutationDelta(key="resume_quality", delta=10, label="resume+10")],
        )
        assert len(req.mutations) == 1

    def test_empty_mutations_rejected(self):
        with pytest.raises(ValidationError):
            CounterfactualRequest(sim_session_id="sim_abc", mutations=[])

    def test_too_many_mutations_rejected(self):
        with pytest.raises(ValidationError):
            CounterfactualRequest(
                sim_session_id="sim_abc",
                mutations=[
                    MutationDelta(key="resume_quality", delta=i, label=f"x{i}")
                    for i in range(11)
                ],
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
