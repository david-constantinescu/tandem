"""Sharing a trip with family: invite links, read-only access for members, and nothing leaks to strangers."""
from __future__ import annotations

from app.extensions import db
from app.models import TripInvite


def _first_trip(api) -> dict:
    return api.get("/api/v1/trips").get_json()["data"][0]


def _second_user(app):
    """a different signed-in person in a separate client"""
    from tests.conftest import ApiClient

    other = ApiClient(app.test_client())
    other.register(email="family@example.com")
    return other


def test_invite_link_lets_family_see_the_trip_but_not_change_or_open_documents(user_api, app):
    trip = user_api.post("/api/v1/trips", json={"name": "Lisbon weekend", "start_date": "2027-03-05",
                                                "end_date": "2027-03-08", "primary_destination": "Lisbon"}).get_json()["data"]
    link = user_api.post(f"/api/v1/trips/{trip['id']}/invites").get_json()["data"]
    token = link["url"].rsplit("/", 1)[1]
    assert "/join/" in link["url"]

    family = _second_user(app)
    assert family.get("/api/v1/trips").get_json()["data"] == []
    assert family.get(f"/api/v1/trips/{trip['id']}").status_code == 404  # no access before joining

    preview = family.get(f"/api/v1/invites/{token}").get_json()["data"]
    assert preview["trip_name"] == "Lisbon weekend" and preview["already_in"] is False
    joined = family.post(f"/api/v1/invites/{token}/accept").get_json()["data"]
    assert joined == {"trip_id": trip["id"], "joined": True}
    assert family.post(f"/api/v1/invites/{token}/accept").get_json()["data"]["joined"] is False  # second time is harmless

    listed = family.get("/api/v1/trips").get_json()["data"]
    assert [t["id"] for t in listed] == [trip["id"]] and listed[0]["role"] == "member"
    assert family.get(f"/api/v1/trips/{trip['id']}/itinerary").status_code == 200
    assert family.get(f"/api/v1/trips/{trip['id']}/reservations").status_code == 200
    assert family.get(f"/api/v1/trips/{trip['id']}/documents").get_json()["data"] == []
    # read-only: everything that changes the trip stays with the owner
    assert family.patch(f"/api/v1/trips/{trip['id']}", json={"name": "Mine now"}).status_code == 404
    assert family.delete(f"/api/v1/trips/{trip['id']}").status_code == 404
    assert family.post(f"/api/v1/trips/{trip['id']}/invites").status_code == 404

    sharing = user_api.get(f"/api/v1/trips/{trip['id']}/sharing").get_json()["data"]
    assert len(sharing["members"]) == 1 and sharing["invites"]
    assert family.get(f"/api/v1/trips/{trip['id']}/sharing").get_json()["data"]["invites"] == []  # links stay private
    notes = user_api.get("/api/v1/notifications").get_json()["data"]
    assert any("joined" in n["title"] or "alăturat" in n["title"] for n in notes)


def test_revoked_or_unknown_links_look_the_same_and_leaving_works(user_api, app):
    trip = user_api.post("/api/v1/trips", json={"name": "Porto"}).get_json()["data"]
    link = user_api.post(f"/api/v1/trips/{trip['id']}/invites").get_json()["data"]
    token = link["url"].rsplit("/", 1)[1]
    family = _second_user(app)
    assert family.post(f"/api/v1/invites/{token}/accept").status_code == 200
    # the member can leave; the owner can remove anyone
    me = family.get("/api/v1/auth/me").get_json()["data"]["user"]
    assert family.delete(f"/api/v1/trips/{trip['id']}/members/{me['id']}").status_code == 200
    assert family.get(f"/api/v1/trips/{trip['id']}").status_code == 404

    assert user_api.delete(f"/api/v1/trips/{trip['id']}/invites/{link['id']}").status_code == 200
    gone = family.post(f"/api/v1/invites/{token}/accept")
    unknown = family.post("/api/v1/invites/not-a-real-token/accept")
    assert gone.status_code == unknown.status_code == 404
    assert gone.get_json()["error"]["code"] == unknown.get_json()["error"]["code"] == "invite_invalid"


def test_expired_invite_is_refused(user_api, app):
    from datetime import timedelta

    from app.utils.timeutil import utcnow

    trip = user_api.post("/api/v1/trips", json={"name": "Nice"}).get_json()["data"]
    link = user_api.post(f"/api/v1/trips/{trip['id']}/invites").get_json()["data"]
    invite = db.session.execute(db.select(TripInvite)).scalar_one()
    invite.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    family = _second_user(app)
    assert family.post(f"/api/v1/invites/{link['url'].rsplit('/', 1)[1]}/accept").status_code == 404
