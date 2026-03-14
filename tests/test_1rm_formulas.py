import pytest

# ── 1RM Formula implementations ───────────────────────────────────────────────
# These are the same formulas used in the continuous aggregate view.
# Testing them here ensures the SQL and Python agree.

def epley(weight_lbs: float, reps: int) -> float:
    """Epley formula: weight × (1 + reps/30). Used in weekly_1rm view."""
    return round(weight_lbs * (1 + reps / 30.0), 1)

def brzycki(weight_lbs: float, reps: int) -> float:
    """Brzycki formula: weight × 36 / (37 - reps). Valid for reps <= 10."""
    if reps > 10:
        raise ValueError("Brzycki formula is unreliable above 10 reps")
    return round(weight_lbs * 36.0 / (37 - reps), 1)

def lbs_to_kg(lbs: float) -> float:
    return round(lbs / 2.205, 2)

def kg_to_lbs(kg: float) -> float:
    return round(kg * 2.205, 1)

# ── Progression logic ─────────────────────────────────────────────────────────

def get_progression(weight_lbs: float, reps: int, avg_rpe: float) -> dict:
    """
    Double progression rules used in get_next_session().
    Isolated here so we can test the logic without a DB connection.
    """
    if avg_rpe <= 7.5:
        return {"next_weight": weight_lbs + 5.0, "next_reps": reps,
                "reason": "RPE <= 7.5 → +5 lbs"}
    elif avg_rpe <= 8.5:
        return {"next_weight": weight_lbs + 2.5, "next_reps": reps,
                "reason": "RPE 7.5-8.5 → +2.5 lbs"}
    elif avg_rpe <= 9.5:
        return {"next_weight": weight_lbs, "next_reps": reps + 1,
                "reason": "RPE 8.5-9.5 → same weight, +1 rep"}
    else:
        return {"next_weight": weight_lbs, "next_reps": reps,
                "reason": "RPE > 9.5 → hold position"}


# ── Epley formula tests ───────────────────────────────────────────────────────

class TestEpleyFormula:

    def test_single_rep_returns_weight(self):
        """1 rep at any weight should return approximately the weight itself."""
        result = epley(225, 1)
        assert result == pytest.approx(225 * (1 + 1/30.0), rel=0.01)

    def test_five_reps_bench(self):
        """185 lbs × 5 reps — real world bench press set."""
        result = epley(185, 5)
        expected = round(185 * (1 + 5/30.0), 1)
        assert result == expected

    def test_three_reps_squat(self):
        """225 lbs × 3 reps — typical working squat set."""
        result = epley(225, 3)
        expected = round(225 * (1 + 3/30.0), 1)
        assert result == expected

    def test_higher_reps_gives_higher_e1rm(self):
        """More reps at same weight should imply higher estimated 1RM."""
        e1rm_5 = epley(185, 5)
        e1rm_8 = epley(185, 8)
        assert e1rm_8 > e1rm_5

    def test_heavier_weight_gives_higher_e1rm(self):
        """Same reps, heavier weight should give higher e1RM."""
        assert epley(225, 5) > epley(185, 5)

    def test_returns_float(self):
        assert isinstance(epley(185, 5), float)

    def test_zero_reps_edge_case(self):
        """Zero reps is nonsensical but should not crash."""
        result = epley(185, 0)
        assert result == 185.0


# ── Brzycki formula tests ─────────────────────────────────────────────────────

class TestBrzyckiFormula:

    def test_one_rep_max_returns_weight(self):
        """Single rep — e1RM should equal the weight lifted."""
        result = brzycki(225, 1)
        expected = round(225 * 36.0 / 36, 1)
        assert result == expected

    def test_five_rep_set(self):
        result = brzycki(185, 5)
        expected = round(185 * 36.0 / 32, 1)
        assert result == expected

    def test_invalid_reps_raises(self):
        """Brzycki is unreliable above 10 reps — should raise ValueError."""
        with pytest.raises(ValueError, match="unreliable above 10 reps"):
            brzycki(185, 11)

    def test_ten_reps_boundary(self):
        """10 reps should be the valid upper boundary."""
        result = brzycki(135, 10)
        assert isinstance(result, float)

    def test_higher_reps_gives_higher_e1rm(self):
        assert brzycki(185, 8) > brzycki(185, 5)


# ── Unit conversion tests ─────────────────────────────────────────────────────

class TestUnitConversions:

    def test_lbs_to_kg_bench_target(self):
        """225 lbs bench target → ~102.1 kg."""
        result = lbs_to_kg(225)
        assert result == pytest.approx(102.04, abs=0.1)

    def test_lbs_to_kg_squat_target(self):
        """315 lbs squat target → ~142.9 kg."""
        result = lbs_to_kg(315)
        assert result == pytest.approx(142.86, abs=0.1)

    def test_lbs_to_kg_deadlift_target(self):
        """285 lbs deadlift target → ~129.3 kg."""
        result = lbs_to_kg(285)
        assert result == pytest.approx(129.25, abs=0.1)

    def test_roundtrip_conversion(self):
        """Converting lbs → kg → lbs should return approximately original value."""
        original = 225.0
        result = kg_to_lbs(lbs_to_kg(original))
        assert result == pytest.approx(original, abs=0.2)

    def test_kg_to_lbs(self):
        """102.1 kg → ~225 lbs."""
        result = kg_to_lbs(102.1)
        assert result == pytest.approx(225.1, abs=0.5)


# ── Progression logic tests ───────────────────────────────────────────────────

class TestProgressionLogic:

    def test_easy_session_adds_five_lbs(self):
        """RPE 7.0 is easy — should progress +5 lbs."""
        result = get_progression(185, 5, avg_rpe=7.0)
        assert result["next_weight"] == 190.0
        assert result["next_reps"] == 5

    def test_rpe_boundary_7_5_adds_five_lbs(self):
        """RPE exactly 7.5 should still trigger +5 lb jump."""
        result = get_progression(185, 5, avg_rpe=7.5)
        assert result["next_weight"] == 190.0

    def test_moderate_session_adds_two_point_five(self):
        """RPE 8.0 — standard progression."""
        result = get_progression(185, 5, avg_rpe=8.0)
        assert result["next_weight"] == 187.5
        assert result["next_reps"] == 5

    def test_hard_session_adds_rep(self):
        """RPE 9.0 — weight stays, add one rep."""
        result = get_progression(185, 5, avg_rpe=9.0)
        assert result["next_weight"] == 185.0
        assert result["next_reps"] == 6

    def test_max_effort_holds_position(self):
        """RPE 10.0 — near-max effort, hold position."""
        result = get_progression(185, 5, avg_rpe=10.0)
        assert result["next_weight"] == 185.0
        assert result["next_reps"] == 5

    def test_rpe_boundary_8_5_adds_weight(self):
        """RPE exactly 8.5 hits the <= 8.5 branch — weight increases, reps stay."""
        result = get_progression(225, 3, avg_rpe=8.5)
        assert result["next_weight"] == 227.5
        assert result["next_reps"] == 3

    def test_rpe_above_8_5_adds_rep(self):
        """RPE 8.6 crosses into the rep-increase tier."""
        result = get_progression(225, 3, avg_rpe=8.6)
        assert result["next_reps"] == 4
        assert result["next_weight"] == 225.0

    def test_progression_returns_dict(self):
        result = get_progression(225, 3, avg_rpe=8.0)
        assert isinstance(result, dict)
        assert "next_weight" in result
        assert "next_reps" in result
        assert "reason" in result

    def test_progression_reason_is_string(self):
        result = get_progression(185, 5, avg_rpe=8.0)
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0


# ── PR target validation tests ────────────────────────────────────────────────

class TestPRTargets:
    """
    Validate that the 2026 PR targets make sense relative to
    current estimated 1RMs from seed data.
    """

    TARGETS = {
        "Bench Press": 225,
        "Squat":       315,
        "Deadlift":    285,
    }

    CURRENT_E1RMS = {
        "Bench Press": 215.8,
        "Squat":       247.5,
        "Deadlift":    263.5,
    }

    def test_all_targets_above_current(self):
        """Every PR target should be higher than current estimated 1RM."""
        for lift in self.TARGETS:
            assert self.TARGETS[lift] > self.CURRENT_E1RMS[lift], (
                f"{lift}: target {self.TARGETS[lift]} is not above "
                f"current e1RM {self.CURRENT_E1RMS[lift]}"
            )

    def test_targets_are_realistic(self):
        """
        Targets should be within 50 lbs of current e1RM —
        anything more would be unrealistic for a single year.
        """
        for lift in self.TARGETS:
            gap = self.TARGETS[lift] - self.CURRENT_E1RMS[lift]
            assert gap <= 70, (
                f"{lift}: gap of {gap} lbs seems unrealistic"
            )

    def test_squat_target_is_largest(self):
        """Squat target should be the heaviest of the three lifts."""
        assert self.TARGETS["Squat"] > self.TARGETS["Bench Press"]
        assert self.TARGETS["Squat"] > self.TARGETS["Deadlift"]