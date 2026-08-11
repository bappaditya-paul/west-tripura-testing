from backend.services.confidence_service import ConfidenceScorer
from backend.services.intent_router import Intent, IntentRouter
from backend.services.query_analysis import QueryAnalyzer


def test_fast_conversation_routes_without_rag():
    router = IntentRouter()
    assert router.route("hello") == Intent.CONVERSATIONAL
    assert router.route("ধন্যবাদ") == Intent.CONVERSATIONAL


def test_simple_contact_query_routes_fast_path():
    assert IntentRouter().route("DM office phone number") == Intent.SIMPLE_FACT


def test_query_analysis_extracts_office_and_contact_metadata():
    analysis = QueryAnalyzer().analyze("dm er number ta ki")
    assert analysis.language == "bn_en"
    assert "District Magistrate" in analysis.entities
    assert analysis.topic == "contact"
    assert analysis.filters["district"] == "West Tripura"


def test_confidence_is_low_without_candidates():
    confidence = ConfidenceScorer().score("DM phone", [])
    assert confidence.level == "low"
    assert confidence.score == 0.0
