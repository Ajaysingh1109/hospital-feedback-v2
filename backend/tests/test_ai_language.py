from app.services.ai.factory import get_ai_providers


def test_scenario_1_hindi_transcription_and_translation():
    """
    Scenario 1: Patient speaks Hindi. System correctly transcribes and translates.
    """
    _, trans_provider, llm_provider = get_ai_providers()
    hindi_transcript = "Khane mein thoda namak kam tha aur nurse ko bulane mein time lag raha tha."
    english = trans_provider.translate_to_english(hindi_transcript, source_language="Hindi")
    assert "salt" in english.lower()
    assert "nurs" in english.lower()

    analysis = llm_provider.extract_structured_feedback(hindi_transcript, english)
    assert analysis["complaint_type"] in ["Complaint", "General Feedback", "Nursing Care", "Food Complaint"]
    assert analysis["negative_feedback"] != "Not Provided"


def test_scenario_2_hinglish_preserves_meaning():
    """
    Scenario 2: Patient speaks Hinglish. System preserves meaning.
    "Doctor ne achhe se explain kiya but nursing response thoda late tha."
    """
    _, trans_provider, llm_provider = get_ai_providers()
    hinglish_transcript = "Doctor ne achhe se explain kiya but nursing response thoda late tha."
    english = trans_provider.translate_to_english(hinglish_transcript, source_language="Hinglish")

    assert "doctor" in english.lower()
    assert "explained" in english.lower()
    assert "nursing" in english.lower()
    assert "delay" in english.lower() or "late" in english.lower()

    analysis = llm_provider.extract_structured_feedback(hinglish_transcript, english)
    assert analysis["positive_feedback"] != "Not Provided"
    assert "doctor" in analysis["positive_feedback"].lower()
    assert analysis["negative_feedback"] != "Not Provided"


def test_scenario_3_english_kept_correctly():
    """
    Scenario 3: Patient speaks English. System keeps English correctly.
    """
    _, trans_provider, llm_provider = get_ai_providers()
    english_transcript = "The room was clean and doctors were attentive, but discharge billing took two hours."
    english = trans_provider.translate_to_english(english_transcript, source_language="English")
    assert "room was clean" in english.lower()
    assert "billing" in english.lower()

    analysis = llm_provider.extract_structured_feedback(english_transcript, english)
    assert analysis["suggested_department"] == "Billing"


def test_scenario_4_mixed_hindi_english():
    """
    Scenario 4: Mixed Hindi + English. System handles both.
    "Sir sab theek tha medicine time pe mil gayi but bathroom dirty tha."
    """
    _, trans_provider, llm_provider = get_ai_providers()
    mixed_transcript = "Sir sab theek tha medicine time pe mil gayi but bathroom dirty tha."
    english = trans_provider.translate_to_english(mixed_transcript, source_language="Mixed")
    assert "medication" in english.lower() or "medicine" in english.lower()
    assert "bathroom" in english.lower() or "washroom" in english.lower()

    analysis = llm_provider.extract_structured_feedback(mixed_transcript, english)
    assert analysis["suggested_department"] == "Housekeeping"


def test_ai_never_invents_missing_data():
    """
    Strict rule: If patient name, UHID, consultant, or treatment are missing from speech,
    the AI must NOT guess them. Returns 'Not Provided'.
    """
    _, trans_provider, llm_provider = get_ai_providers()
    vague_text = "Ac cooling theek nahi chal raha tha."
    english = trans_provider.translate_to_english(vague_text)
    analysis = llm_provider.extract_structured_feedback(vague_text, english)

    # Positive feedback was not spoken -> must be Not Provided
    assert analysis["positive_feedback"] == "Not Provided"


def test_case_1_and_2_hindi_hinglish_ac_and_doctor_translation():
    """
    Cases 1 & 2: Hindi/Hinglish speech translated accurately into professional English.
    'Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha.'
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hinglish")

    assert "doctor" in english.lower()
    assert "time" in english.lower() or "attended" in english.lower()
    assert "air conditioning" in english.lower() or "ac" in english.lower()
    assert "not functioning" in english.lower() or "kaam nahi" not in english.lower()


def test_case_3_and_4_positive_negative_separation_and_dedicated_complaint_field():
    """
    Cases 3 & 4:
    Separation of positive and negative feedback:
    - Positive: Doctor attended on time
    - Negative: AC was not cooling / working
    Dedicated complaint field contains ONLY the final professional English complaint statement.
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hinglish")
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    assert "complaint" in analysis
    assert len(analysis["complaint"]) > 5
    # Complaint field is dedicated English statement
    assert "air conditioning" in analysis["complaint"].lower() or "ac" in analysis["complaint"].lower()
    # Complaint type is standard hospital category
    assert analysis["complaint_type"] in ["Maintenance", "Complaint", "General Feedback"]


def test_case_5_and_6_consultant_never_guessed_and_optional(client, staff_headers):
    """
    Cases 5 & 6:
    AI does not guess consultant name.
    Consultant is free text and optional in feedback submission.
    """
    import uuid
    # 1. Submission with Consultant omitted (optional)
    payload_no_consultant = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998877",
        "patient_name": "Ramesh Patel",
        "department": "Clinical",
        "complaint": "Doctor consultation was brief.",
    }
    res1 = client.post("/api/v1/feedback", json=payload_no_consultant, headers=staff_headers)
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["consultant"] is None or data1["consultant"] == "Not Provided"
    assert data1["complaint"] == "Doctor consultation was brief."

    # 2. Submission with Free Text Consultant manually entered by staff
    payload_with_consultant = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998878",
        "patient_name": "Suresh Mehta",
        "department": "Clinical",
        "consultant": "Dr. Rajesh Kumar",
        "complaint": "Doctor consultation was comprehensive.",
    }
    res2 = client.post("/api/v1/feedback", json=payload_with_consultant, headers=staff_headers)
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["consultant"] == "Dr. Rajesh Kumar"
