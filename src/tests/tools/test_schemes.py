"""Tests for government scheme eligibility tool."""
import pytest
from app.tools.schemes import check_scheme_eligibility, _classify_farmer


class TestClassifyFarmer:
    def test_marginal_farmer(self):
        assert _classify_farmer(1.5) == "marginal"

    def test_small_farmer(self):
        assert _classify_farmer(4.0) == "small"

    def test_large_farmer(self):
        assert _classify_farmer(10.0) == "large"

    def test_zero_land(self):
        assert _classify_farmer(0) == "marginal"

    def test_boundary_marginal(self):
        assert _classify_farmer(2.5) == "marginal"

    def test_boundary_small(self):
        assert _classify_farmer(5.0) == "small"


class TestCheckSchemeEligibility:
    def test_returns_schemes_for_state(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert "schemes" in result
        assert len(result["schemes"]) > 0
        names = [s["name"] for s in result["schemes"]]
        assert any("PM-KISAN" in n for n in names)

    def test_returns_state_specific_schemes(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        names = [s["name"] for s in result["schemes"]]
        assert any("Rythu Bandhu" in n for n in names)

    def test_excludes_other_state_schemes(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        names = [s["name"] for s in result["schemes"]]
        assert not any("KALIA" in n for n in names)

    def test_filters_by_land_holding(self):
        result = check_scheme_eligibility({"state": "Odisha", "land_holding": 10})
        names = [s["name"] for s in result["schemes"]]
        assert not any("KALIA" in n.upper() for n in names)

    def test_no_state_returns_central_only(self):
        result = check_scheme_eligibility({})
        assert "schemes" in result
        for s in result["schemes"]:
            assert s.get("type") == "central"

    def test_limits_to_five_results(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert len(result["schemes"]) <= 5

    def test_total_matched_count(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert "total_matched" in result
        assert result["total_matched"] >= len(result["schemes"])

    def test_scheme_has_required_fields(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        for scheme in result["schemes"]:
            assert "name" in scheme
            assert "benefits" in scheme
            assert "how_to_apply" in scheme
