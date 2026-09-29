from app.ai_job_search.providers.adzuna import (
    matches_selected_locations,
    normalize_india_search_locations,
    provider_location_term,
)


def test_bengaluru_ui_label_uses_provider_friendly_term():
    assert provider_location_term("Bengaluru (Bangalore)") == "Bengaluru"


def test_bengaluru_selection_accepts_bengaluru_and_bangalore_aliases():
    selected = ["Bengaluru (Bangalore)"]

    assert matches_selected_locations("Bengaluru, Karnataka", selected)
    assert matches_selected_locations("Bangalore Urban, Karnataka", selected)


def test_bengaluru_selection_rejects_other_indian_cities():
    selected = ["Bengaluru (Bangalore)"]

    assert not matches_selected_locations("Hyderabad, Telangana", selected)
    assert not matches_selected_locations("Pune, Maharashtra", selected)


def test_multiple_selected_locations_are_or_based():
    selected = ["Bengaluru (Bangalore)", "Hyderabad"]

    assert matches_selected_locations("Hyderabad, Telangana", selected)
    assert matches_selected_locations("Bengaluru / Hyderabad", selected)
    assert not matches_selected_locations("Mumbai, Maharashtra", selected)


def test_no_valid_city_constraint_searches_all_india():
    assert normalize_india_search_locations([]) == ["India"]
    assert normalize_india_search_locations(["San Francisco, CA", "Remote"]) == ["India"]
    assert provider_location_term("India") == ""


def test_all_india_accepts_other_indian_cities_but_rejects_foreign_locations():
    assert matches_selected_locations("Bhubaneswar, Odisha", ["India"])
    assert matches_selected_locations("Remote - India", ["India"])
    assert not matches_selected_locations("Singapore", ["India"])
    assert not matches_selected_locations("Remote - Worldwide", ["India"])
