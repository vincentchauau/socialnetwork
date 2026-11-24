from tests.job.conftest import ALICE, BOB, job_body, post_job


def test_a_posting_keeps_its_details_and_shows_them_on_its_page(client):
    made = post_job(
        client,
        company_about="A research platform for scientists.",
        domain="Scientific search",
        work_mode="hybrid",
        timezone="ICT (UTC+7)",
        working_hours="Core hours 7:30 PM to 9:30 PM",
        contract_until="2027-07-31",
        people_managed=3,
        nationality_required="Vietnamese",
        requirements="Five years of production full-stack work.",
        nice_to_have="Experience with LLM agents.",
        hiring_process="Screening, technical interview, final interview.",
        application_requirements="A portfolio and one case study.",
    )

    page = client.get(f"/jobs/{made['id']}", headers=BOB).json()

    assert page["work_mode"] == "hybrid"
    assert page["contract_until"] == "2027-07-31"
    assert page["people_managed"] == 3
    assert page["nationality_required"] == "Vietnamese"
    assert page["hiring_process"] == "Screening, technical interview, final interview."


def test_the_new_details_are_optional_and_empty_by_default(client):
    made = post_job(client)

    page = client.get(f"/jobs/{made['id']}", headers=ALICE).json()

    assert page["work_mode"] is None and page["contract_until"] is None
    assert page["people_managed"] == 0 and page["requirements"] == ""


def test_work_mode_takes_only_the_three_kinds(client):
    response = client.post("/jobs", json={**job_body(), "work_mode": "anywhere"}, headers=ALICE)

    assert response.status_code == 422


def test_the_owner_can_change_a_detail_and_clear_a_text_detail_is_refused(client):
    made = post_job(client)

    changed = client.patch(f"/jobs/{made['id']}", json={"working_hours": "Flexible"}, headers=ALICE)
    assert changed.status_code == 200 and changed.json()["working_hours"] == "Flexible"

    refused = client.patch(f"/jobs/{made['id']}", json={"requirements": None}, headers=ALICE)
    assert refused.status_code == 422
