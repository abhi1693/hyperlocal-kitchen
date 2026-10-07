"""Database-free checks of the MVP's public contracts and admin route boundary."""

from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from kitchen_admin_api.main import create_app as admin_app
from kitchen_api.main import create_app as resident_app
from kitchen_core.db import get_session
from kitchen_core.models import Base, Community, Dish, MenuListing, Order
from kitchen_http.auth import require_admin, require_user


def test_removed_mvp_fields_are_absent_from_storage_and_client_contracts():
    community_fields = {"timezone", "access_instructions"}
    dish_fields = {"dietary_type", "allergens", "portion_description"}
    assert community_fields.isdisjoint(Community.__table__.columns.keys())
    assert dish_fields.isdisjoint(Dish.__table__.columns.keys())
    assert "customer_name" not in Order.__table__.columns
    assert {
        "kitchen_name",
        "accepted_at",
        "preparing_at",
        "ready_at",
        "completed_at",
        "cancelled_at",
        "rejected_at",
        "rejection_reason",
    }.isdisjoint(Order.__table__.columns.keys())
    assert "delivery_fee_paise" not in MenuListing.__table__.columns
    assert not any("audit" in name for name in Base.metadata.tables)

    for app in (resident_app(), admin_app()):
        schemas = app.openapi()["components"]["schemas"]
        for name in ("CommunityCreate", "CommunityUpdate", "CommunityOut"):
            if name in schemas:
                assert community_fields.isdisjoint(schemas[name]["properties"])
        for name in ("DishCreate", "DishUpdate", "DishOut"):
            if name in schemas:
                assert dish_fields.isdisjoint(schemas[name]["properties"])
        if "OrderCreate" in schemas:
            assert "customer_name" not in schemas["OrderCreate"]["properties"]
        for name in ("ListingCreate", "ListingUpdate"):
            if name in schemas:
                assert "delivery_fee_paise" not in schemas[name]["properties"]
        for name in (
            "CommunityCreate",
            "CommunityUpdate",
            "DishCreate",
            "DishUpdate",
            "OrderCreate",
        ):
            if name in schemas:
                assert schemas[name]["additionalProperties"] is False


def test_community_and_zone_writes_exist_only_in_platform_admin_api():
    resident_paths = resident_app().openapi()["paths"]
    admin = admin_app()
    admin_paths = admin.openapi()["paths"]
    for method, path in (
        ("post", "/api/v1/communities"),
        ("post", "/api/v1/communities/{community_id}/zones"),
    ):
        assert method in admin_paths[path]
        assert method not in resident_paths.get(path, {})


def test_all_admin_resources_require_platform_admin_access():
    app = admin_app()
    operations = []
    paths = []
    for route in iter_route_contexts(app.routes):
        if (
            isinstance(route.original_route, APIRoute)
            and route.path is not None
            and route.path.startswith("/api/v1/")
            and not route.path.startswith("/api/v1/auth/")
        ):
            assert any(
                dependency.call is require_admin for dependency in route.dependant.dependencies
            ), route.path
            operations.append(route.operation_id or route.unique_id)
            paths.extend((method, route.path) for method in route.methods)
    assert operations
    assert len(operations) == len(set(operations))
    assert len(paths) == len(set(paths))
    assert not any("/admin/" in path for path in app.openapi()["paths"])

    with TestClient(app) as client:
        for method, path in paths:
            resolved = path
            for parameter in path.split("/"):
                if parameter.startswith("{"):
                    resolved = resolved.replace(parameter, "00000000-0000-0000-0000-000000000001")
            response = client.request(method, resolved, json={})
            assert response.status_code == 401, (method, path, response.text)


def test_discovery_contract_does_not_expose_private_fulfillment_details():
    schemas = resident_app().openapi()["components"]["schemas"]
    assert {"address_label", "phone", "upi_id"}.isdisjoint(schemas["KitchenOut"]["properties"])
    paths = resident_app().openapi()["paths"] | admin_app().openapi()["paths"]
    assert not any("audit" in path or "support" in path for path in paths)


def test_residents_join_directly_and_legacy_approval_and_invitations_are_removed():
    assert not any("invitation" in name for name in Base.metadata.tables)
    resident = resident_app()
    admin = admin_app()
    resident_contract = resident.openapi()
    admin_contract = admin.openapi()
    join_schema = resident_contract["components"]["schemas"]["MembershipJoin"]
    assert set(join_schema["properties"]) == {"zone_id", "address_label"}
    assert join_schema["additionalProperties"] is False
    assert "post" in admin_contract["paths"]["/api/v1/memberships/{membership_id}/activate"]
    assert "post" in admin_contract["paths"]["/api/v1/kitchens/{kitchen_id}/approve"]
    for contract in (resident_contract, admin_contract):
        assert not any("invitation" in path for path in contract["paths"])
        assert "/api/v1/memberships/{membership_id}/approve" not in contract["paths"]

    identifier = "00000000-0000-0000-0000-000000000001"
    for app in (resident, admin):
        with TestClient(app) as client:
            for method, path in (
                ("get", "/api/v1/invitations"),
                ("get", f"/api/v1/invitations/{identifier}"),
                ("delete", f"/api/v1/invitations/{identifier}"),
                ("get", f"/api/v1/communities/{identifier}/invitations"),
                ("post", f"/api/v1/communities/{identifier}/invitations"),
                ("post", f"/api/v1/memberships/{identifier}/approve"),
            ):
                response = client.request(method, path, json={})
                assert response.status_code == 404, (method, path, response.text)

    resident.dependency_overrides[require_user] = lambda: None
    resident.dependency_overrides[get_session] = lambda: None
    with TestClient(resident) as client:
        response = client.post(
            f"/api/v1/communities/{identifier}/join",
            json={"zone_id": identifier, "address_label": "A-101", "invitation_code": "a" * 32},
        )
        assert response.status_code == 422
        assert any(
            field["loc"] == ["body", "invitation_code"] and field["type"] == "extra_forbidden"
            for field in response.json()["detail"]["fields"]
        )


def test_unsupported_database_text_returns_validation_errors_before_queries():
    app = admin_app()
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_session] = lambda: None
    with TestClient(app) as client:
        assert client.get("/api/v1/users", params={"q": "\x00"}).status_code == 422
        for path, payload in (
            ("/api/v1/users/00000000-0000-0000-0000-000000000001", {"name": "bad\x00name"}),
            ("/api/v1/zones/00000000-0000-0000-0000-000000000001", {"name": "bad\x00name"}),
        ):
            assert client.patch(path, json=payload).status_code == 422


def test_community_choice_contract_preserves_slugs_and_exposes_labels():
    import pytest
    from kitchen_core.catalog_schemas import CommunityCreate, CommunityUpdate
    from pydantic import ValidationError

    for app in (resident_app(), admin_app()):
        schema = app.openapi()["components"]["schemas"]["CommunityType"]
        choices = schema["x-choices"]
        assert [choice["slug"] for choice in choices] == schema["enum"]
        assert {"slug": "residential_society", "label": "Residential society"} in choices
        assert len({choice["slug"] for choice in choices}) == 7
    payload = CommunityCreate(name="Home", city="Pune", type="residential_society")
    assert payload.model_dump(mode="json")["type"] == "residential_society"
    assert CommunityCreate(name="Home", city="Pune").type == "residential_society"
    assert CommunityUpdate(type=None).model_dump(mode="json")["type"] is None
    with pytest.raises(ValidationError):
        CommunityCreate(name="Home", city="Pune", type="Residential society")
