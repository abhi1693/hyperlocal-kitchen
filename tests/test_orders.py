from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from kitchen_core import catalog
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Community,
    CommunityZone,
    Dish,
    Kitchen,
    KitchenMember,
    ListingPickupPoint,
    Membership,
    MenuListing,
    Notification,
    Order,
    OrderEvent,
    OrderItem,
    PickupPoint,
    User,
)
from kitchen_core.order_schemas import OrderCreate
from kitchen_core.orders import (
    create_order,
    expire_order,
    get_order,
    list_customer_orders,
    list_kitchen_orders,
    record_payment,
    transition_order,
)
from sqlalchemy import event, func, select, text


def attach_pickup(session, kitchen, listing):
    point = session.scalar(select(PickupPoint).where(PickupPoint.kitchen_id == kitchen.id))
    if point is None:
        point = PickupPoint(
            community_id=kitchen.community_id,
            kitchen_id=kitchen.id,
            zone_id=kitchen.zone_id,
            name=kitchen.name,
            address_label=kitchen.address_label,
        )
        session.add(point)
        session.flush()
    session.add(
        ListingPickupPoint(
            listing_id=listing.id,
            pickup_point_id=point.id,
            kitchen_id=kitchen.id,
            community_id=kitchen.community_id,
        )
    )
    session.flush()
    return point


@pytest.fixture
def order_seed(session_factory):
    now = datetime.now(UTC)
    with session_factory() as session:
        community = Community(
            name="Oak Community",
            address="Oak Road",
            city="Gurugram",
            postal_code="122001",
            status="active",
        )
        other_community = Community(
            name="Other Community",
            address="Other Road",
            city="Gurugram",
            postal_code="122001",
            status="active",
        )
        owner = User(oidc_subject="owner", oidc_issuer="https://auth.example.test", name="Manisha")
        customer = User(
            oidc_subject="resident-one",
            oidc_issuer="https://auth.example.test",
            name="Resident One",
        )
        customer_two = User(
            oidc_subject="resident-two",
            oidc_issuer="https://auth.example.test",
            name="Resident Two",
        )
        outsider = User(
            oidc_subject="outsider", oidc_issuer="https://auth.example.test", name="Outsider"
        )
        session.add_all([community, other_community, owner, customer, customer_two, outsider])
        session.flush()
        zone = CommunityZone(community_id=community.id, name="Zone B")
        other_zone = CommunityZone(community_id=other_community.id, name="Zone A")
        session.add_all([zone, other_zone])
        session.flush()
        memberships = [
            Membership(
                community_id=community.id,
                user_id=user.id,
                zone_id=zone.id,
                address_label=f"B-{100 + index}",
                status="active",
            )
            for index, user in enumerate([owner, customer, customer_two])
        ]
        session.add_all(memberships)
        session.add(
            Membership(
                community_id=other_community.id,
                user_id=outsider.id,
                zone_id=other_zone.id,
                address_label="A-101",
                status="active",
            )
        )
        kitchen = Kitchen(
            community_id=community.id,
            name="Manisha's Kitchen",
            zone_id=zone.id,
            address_label="B-100",
            status="approved",
            upi_id="manisha@bank",
        )
        session.add(kitchen)
        session.flush()
        session.add(KitchenMember(kitchen_id=kitchen.id, user_id=owner.id))
        dish = Dish(kitchen_id=kitchen.id, name="Rajma Chawal")
        session.add(dish)
        session.flush()
        listing = MenuListing(
            kitchen_id=kitchen.id,
            dish_id=dish.id,
            service_date=now.date(),
            available_from=now + timedelta(hours=2),
            available_until=now + timedelta(hours=3),
            order_cutoff=now + timedelta(hours=1),
            price_paise=15000,
            quantity_total=15,
        )
        session.add(listing)
        session.flush()
        point = attach_pickup(session, kitchen, listing)
        result = {
            "pickup_point": point.id,
            "community": community.id,
            "zone": zone.id,
            "owner": owner.id,
            "customer": customer.id,
            "customer_two": customer_two.id,
            "outsider": outsider.id,
            "kitchen": kitchen.id,
            "dish": dish.id,
            "listing": listing.id,
            "membership": memberships[1].id,
        }
        session.commit()
        return result


def payload(seed, quantity=2):
    return OrderCreate(items=[{"menu_listing_id": seed["listing"], "quantity": quantity}])


def place(session_factory, seed, quantity=2, key=None, customer=None):
    with session_factory() as session:
        result = create_order(
            session,
            session.get(User, customer or seed["customer"]),
            payload(seed, quantity),
            key or str(uuid4()),
        )
        session.commit()
        return result


def transition(session_factory, seed, order_id, action, reason=None):
    actor = "customer" if action == "cancel" else "owner"
    with session_factory() as session:
        result = transition_order(session, session.get(User, seed[actor]), order_id, action, reason)
        session.commit()
        return result


@pytest.mark.parametrize("admin", [False, True])
def test_pause_blocks_only_new_orders(session_factory, order_seed, admin):
    seed = order_seed
    original = place(session_factory, seed, key="before-pause")
    with session_factory() as session:
        catalog.set_kitchen_accepting_orders(
            session, seed["owner"], seed["kitchen"], accepting=False, reason="Emergency"
        )
        session.commit()
    with session_factory() as session:
        user = session.get(User, seed["customer"])
        replay = create_order(session, user, payload(seed), "before-pause", admin=admin)
        assert replay.id == original.id
        with pytest.raises(DomainError) as error:
            create_order(session, user, payload(seed), "during-pause", admin=admin)
        assert error.value.status == 409
        assert error.value.code == "kitchen_not_accepting_orders"
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.scalar(select(func.count()).select_from(Order)) == 1

    assert transition(session_factory, seed, original.id, "accept").status == "accepted"
    assert transition(session_factory, seed, original.id, "prepare").status == "preparing"
    assert transition(session_factory, seed, original.id, "ready").status == "ready"
    assert transition(session_factory, seed, original.id, "complete").status == "completed"
    with session_factory() as session:
        catalog.set_kitchen_accepting_orders(
            session, seed["owner"], seed["kitchen"], accepting=True
        )
        session.commit()
    assert place(session_factory, seed, key="after-resume").id != original.id


def test_checkout_waits_for_pause_and_refreshes_cached_kitchen(session_factory, order_seed):
    seed = order_seed
    cached = Event()
    proceed = Event()
    checking_kitchen = Event()

    def checkout():
        with session_factory() as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            kitchen = session.get(Kitchen, seed["kitchen"])
            assert kitchen.is_accepting_orders is True
            cached.set()
            assert proceed.wait(timeout=5)

            def before_execute(conn, cursor, statement, parameters, context, executemany):
                if "FROM kitchens" in statement and "FOR SHARE" in statement:
                    checking_kitchen.set()

            event.listen(session.connection(), "before_cursor_execute", before_execute)
            with pytest.raises(DomainError) as error:
                create_order(
                    session, session.get(User, seed["customer"]), payload(seed), "pause-race"
                )
            return error.value.code

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(checkout)
        assert cached.wait(timeout=5)
        with session_factory() as session:
            catalog.set_kitchen_accepting_orders(
                session, seed["owner"], seed["kitchen"], accepting=False
            )
            proceed.set()
            assert checking_kitchen.wait(timeout=5)
            assert not future.done()
            session.commit()
        assert future.result(timeout=5) == "kitchen_not_accepting_orders"
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_create_snapshots_and_canonical_idempotency(session_factory, order_seed):
    seed = order_seed
    duplicate_payload = OrderCreate(
        items=[
            {"menu_listing_id": seed["listing"], "quantity": 1},
            {"menu_listing_id": seed["listing"], "quantity": 1},
        ]
    )
    with session_factory() as session:
        user = session.get(User, seed["customer"])
        original = create_order(session, user, duplicate_payload, "stable-key")
        session.commit()
    assert original.status == "pending"
    assert original.total_paise == 30000
    assert original.upi_id is None
    assert len(original.items) == 1
    assert original.items[0].quantity == 2
    with session_factory() as session:
        user = session.get(User, seed["customer"])
        replay = create_order(session, user, payload(seed), "stable-key")
        assert replay.id == original.id
        with pytest.raises(DomainError, match="different order"):
            create_order(session, user, payload(seed, 3), "stable-key")
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert session.scalar(select(func.count()).select_from(OrderItem)) == 1
        assert session.scalar(select(func.count()).select_from(Notification)) == 1
        session.get(Dish, seed["dish"]).name = "Changed dish"
        session.get(MenuListing, seed["listing"]).price_paise = 90000
        session.get(Kitchen, seed["kitchen"]).address_label = "B-900"
        session.get(Kitchen, seed["kitchen"]).name = "Updated Kitchen"
        session.get(Membership, seed["membership"]).address_label = "B-901"
        session.get(User, seed["customer"]).name = "Updated Resident"
        session.commit()
    with session_factory() as session:
        detail = get_order(session, session.get(User, seed["customer"]), original.id)
        assert detail.items[0].dish_name == "Rajma Chawal"
        assert detail.total_paise == 30000
        assert detail.pickup_address.address_label == "B-100"
        assert detail.delivery_address is None
        assert detail.fulfillment_snapshot.address_label == "B-100"
        assert detail.customer_name == "Updated Resident"
        assert detail.kitchen_name == "Updated Kitchen"


def test_real_postgres_competing_orders_cannot_oversell(session_factory, order_seed):
    seed = order_seed
    with session_factory() as session:
        session.get(MenuListing, seed["listing"]).quantity_total = 1
        session.commit()
    barrier = Barrier(2)

    def submit(customer_id):
        with session_factory() as session:
            user = session.get(User, customer_id)
            barrier.wait(timeout=10)
            try:
                result = create_order(session, user, payload(seed, 1), str(uuid4()))
                session.commit()
                return result.id
            except DomainError as error:
                session.rollback()
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [seed["customer"], seed["customer_two"]]))
    assert outcomes.count("insufficient_quantity") == 1
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 1
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_concurrent_same_key_creates_one_order(session_factory, order_seed):
    seed = order_seed
    barrier = Barrier(2)

    def submit(_):
        with session_factory() as session:
            user = session.get(User, seed["customer"])
            barrier.wait(timeout=10)
            result = create_order(session, user, payload(seed), "concurrent-key")
            session.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [1, 2]))
    assert outcomes[0] == outcomes[1]
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.scalar(select(func.count()).select_from(Order)) == 1


@pytest.mark.parametrize("action,reason", [("cancel", None), ("reject", "Sold out in person")])
def test_release_once_for_repeated_actions(session_factory, order_seed, action, reason):
    order = place(session_factory, order_seed)
    first = transition(session_factory, order_seed, order.id, action, reason)
    replay = transition(session_factory, order_seed, order.id, action, reason)
    assert first.status == replay.status
    assert first.rejection_reason == replay.rejection_reason == reason
    with session_factory() as session:
        assert session.get(MenuListing, order_seed["listing"]).quantity_reserved == 0
        assert (
            session.scalar(
                select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
            )
            == 2
        )


def test_state_machine_completion_consumes_portions(session_factory, order_seed):
    seed = order_seed
    order = place(session_factory, seed)
    with pytest.raises(DomainError) as error:
        transition(session_factory, seed, order.id, "ready")
    assert error.value.status == 409
    accepted = transition(session_factory, seed, order.id, "accept")
    assert accepted.upi_id == "manisha@bank"
    transition(session_factory, seed, order.id, "prepare")
    with pytest.raises(DomainError) as error:
        transition(session_factory, seed, order.id, "cancel")
    assert error.value.status == 409
    transition(session_factory, seed, order.id, "ready")
    completed = transition(session_factory, seed, order.id, "complete")
    assert completed.status == "completed"
    assert [event.status for event in completed.events] == [
        "pending",
        "accepted",
        "preparing",
        "ready",
        "completed",
    ]
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2


def test_cancel_accepted_releases_inventory(session_factory, order_seed):
    order = place(session_factory, order_seed)
    transition(session_factory, order_seed, order.id, "accept")
    assert transition(session_factory, order_seed, order.id, "cancel").status == "cancelled"
    with session_factory() as session:
        assert session.get(MenuListing, order_seed["listing"]).quantity_reserved == 0


def test_expiry_is_once_and_cutoff_bounds_deadline(session_factory, order_seed):
    seed = order_seed
    cutoff = datetime.now(UTC) + timedelta(minutes=2)
    with session_factory() as session:
        session.get(MenuListing, seed["listing"]).order_cutoff = cutoff
        session.commit()
    order = place(session_factory, seed)
    assert order.expires_at == cutoff
    with session_factory() as session:
        assert not expire_order(session, order.id, cutoff - timedelta(seconds=1))
        assert expire_order(session, order.id, cutoff)
        assert not expire_order(session, order.id, cutoff)
        session.commit()
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 0
        assert session.get(Order, order.id).status == "expired"
        assert (
            session.scalar(
                select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
            )
            == 2
        )


def test_payment_recording_is_separate_and_authorized(session_factory, order_seed):
    seed = order_seed
    order = place(session_factory, seed)
    with session_factory() as session:
        with pytest.raises(DomainError) as error:
            record_payment(session, session.get(User, seed["customer"]), order.id, "report")
        assert error.value.status == 409
    transition(session_factory, seed, order.id, "accept")
    with session_factory() as session:
        customer = session.get(User, seed["customer"])
        assert (
            record_payment(session, customer, order.id, "report").payment_status
            == "customer_reported"
        )
        assert (
            record_payment(session, customer, order.id, "report").payment_status
            == "customer_reported"
        )
        session.commit()
    with session_factory() as session:
        with pytest.raises(DomainError) as error:
            record_payment(session, session.get(User, seed["customer"]), order.id, "confirm")
        assert error.value.status == 404
    with session_factory() as session:
        owner = session.get(User, seed["owner"])
        confirmed = record_payment(session, owner, order.id, "confirm")
        assert confirmed.payment_status == "kitchen_confirmed"
        assert confirmed.status == "accepted"
        record_payment(session, owner, order.id, "confirm")
        session.commit()
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert (
            session.scalar(
                select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
            )
            == 4
        )


def test_order_privacy_and_own_history_after_suspension(session_factory, order_seed):
    seed = order_seed
    order = place(session_factory, seed)
    with session_factory() as session:
        outsider = session.get(User, seed["outsider"])
        with pytest.raises(DomainError) as error:
            get_order(session, outsider, order.id)
        assert error.value.status == 404
        assert list_customer_orders(session, outsider).total == 0
        with pytest.raises(DomainError):
            list_kitchen_orders(session, outsider, seed["kitchen"])
        with pytest.raises(DomainError) as error:
            create_order(session, outsider, payload(seed), "outsider-key")
        assert error.value.status == 403
        session.get(Membership, seed["membership"]).status = "suspended"
        session.commit()
    with session_factory() as session:
        customer = session.get(User, seed["customer"])
        assert get_order(session, customer, order.id).id == order.id
        with pytest.raises(DomainError):
            create_order(session, customer, payload(seed), "suspended-key")


@pytest.mark.parametrize(
    "field,value", [("status", "draft"), ("quantity_total", 1), ("order_cutoff", "past")]
)
def test_unavailable_listing_reserves_nothing(session_factory, order_seed, field, value):
    seed = order_seed
    with session_factory() as session:
        listing = session.get(MenuListing, seed["listing"])
        setattr(
            listing, field, datetime.now(UTC) - timedelta(minutes=1) if value == "past" else value
        )
        session.commit()
    with pytest.raises(DomainError):
        place(session_factory, seed)
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 0


@pytest.mark.parametrize("incompatible_window", [False, True])
def test_multi_item_failure_rolls_back_every_reservation(
    session_factory, order_seed, incompatible_window
):
    seed = order_seed
    with session_factory() as session:
        original = session.get(MenuListing, seed["listing"])
        second = MenuListing(
            kitchen_id=original.kitchen_id,
            dish_id=original.dish_id,
            service_date=original.service_date,
            available_from=original.available_from,
            available_until=original.available_until
            + (timedelta(minutes=1) if incompatible_window else timedelta()),
            order_cutoff=original.order_cutoff,
            price_paise=10000,
            quantity_total=1,
        )
        session.add(second)
        session.flush()
        attach_pickup(session, session.get(Kitchen, seed["kitchen"]), second)
        second_id = second.id
        session.commit()
    request = OrderCreate(
        items=[
            {"menu_listing_id": seed["listing"], "quantity": 1},
            {"menu_listing_id": second_id, "quantity": 2},
        ]
    )
    with session_factory() as session:
        with pytest.raises(DomainError) as error:
            create_order(session, session.get(User, seed["customer"]), request, "atomic-key")
        assert error.value.code == (
            "mixed_service_windows" if incompatible_window else "insufficient_quantity"
        )
        session.rollback()
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 0
        assert session.get(MenuListing, second_id).quantity_reserved == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_expiry_can_notify_customer_while_their_new_order_waits_for_stock(
    session_factory, order_seed
):
    seed = order_seed
    old_order = place(session_factory, seed)
    listing_locked = Event()
    customer_locked = Event()

    def expire():
        with session_factory() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            session.scalar(select(Order).where(Order.id == old_order.id).with_for_update())
            session.scalar(
                select(MenuListing).where(MenuListing.id == seed["listing"]).with_for_update()
            )
            listing_locked.set()
            assert customer_locked.wait(timeout=5)
            expired = expire_order(session, old_order.id, old_order.expires_at)
            session.commit()
            return expired

    def order():
        assert listing_locked.wait(timeout=5)
        with session_factory() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))

            def after_query(connection, cursor, statement, parameters, context, executemany):
                if "FROM users" in statement and "FOR " in statement:
                    customer_locked.set()

            event.listen(session.connection(), "after_cursor_execute", after_query)
            created = create_order(
                session,
                session.get(User, seed["customer"]),
                payload(seed),
                "after-expiry-key",
            )
            session.commit()
            return created

    with ThreadPoolExecutor(max_workers=2) as executor:
        expiry_future = executor.submit(expire)
        order_future = executor.submit(order)
        assert expiry_future.result(timeout=10)
        assert order_future.result(timeout=10).status == "pending"
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.get(Order, old_order.id).status == "expired"


def test_kitchen_owners_can_order_from_each_other_without_notification_deadlock(
    session_factory, order_seed
):
    seed = order_seed
    with session_factory() as session:
        original = session.get(MenuListing, seed["listing"])
        second_kitchen = Kitchen(
            community_id=seed["community"],
            name="Second Kitchen",
            zone_id=seed["zone"],
            address_label="B-102",
            status="approved",
        )
        session.add(second_kitchen)
        session.flush()
        session.add(KitchenMember(kitchen_id=second_kitchen.id, user_id=seed["customer_two"]))
        second_dish = Dish(kitchen_id=second_kitchen.id, name="Dal Rice")
        session.add(second_dish)
        session.flush()
        second_listing = MenuListing(
            kitchen_id=second_kitchen.id,
            dish_id=second_dish.id,
            service_date=original.service_date,
            available_from=original.available_from,
            available_until=original.available_until,
            order_cutoff=original.order_cutoff,
            price_paise=10000,
            quantity_total=15,
        )
        session.add(second_listing)
        session.flush()
        attach_pickup(session, second_kitchen, second_listing)
        second_listing_id = second_listing.id
        session.commit()

    both_customers_locked = Barrier(2)

    def order(arguments):
        user_id, listing_id = arguments
        with session_factory() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))

            def after_query(connection, cursor, statement, parameters, context, executemany):
                if "FROM users" in statement and "FOR " in statement:
                    both_customers_locked.wait(timeout=5)

            event.listen(session.connection(), "after_cursor_execute", after_query)
            created = create_order(
                session,
                session.get(User, user_id),
                OrderCreate(items=[{"menu_listing_id": listing_id, "quantity": 2}]),
                str(uuid4()),
            )
            session.commit()
            return created

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(order, arguments)
            for arguments in [
                (seed["owner"], second_listing_id),
                (seed["customer_two"], seed["listing"]),
            ]
        ]
        assert all(future.result(timeout=10).status == "pending" for future in futures)
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.get(MenuListing, second_listing_id).quantity_reserved == 2
        assert session.scalar(select(func.count()).select_from(Order)) == 2


@pytest.mark.parametrize("restricted", ["suspended_membership", "inactive_account"])
def test_new_orders_do_not_notify_managers_without_active_access(
    session_factory, order_seed, restricted
):
    seed = order_seed
    with session_factory() as session:
        session.add(
            KitchenMember(kitchen_id=seed["kitchen"], user_id=seed["customer_two"], role="manager")
        )
        if restricted == "suspended_membership":
            membership = session.scalar(
                select(Membership).where(
                    Membership.user_id == seed["customer_two"],
                    Membership.community_id == seed["community"],
                )
            )
            membership.status = "suspended"
        else:
            session.get(User, seed["customer_two"]).is_active = False
        session.commit()
    order = place(session_factory, seed)
    with session_factory() as session:
        recipients = list(
            session.scalars(select(Notification.user_id).where(Notification.order_id == order.id))
        )
        assert recipients == [seed["owner"]]


def test_delivery_fee_comes_from_kitchen_and_is_snapshotted_per_order(session_factory, order_seed):
    seed = order_seed
    with session_factory() as session:
        kitchen = session.get(Kitchen, seed["kitchen"])
        kitchen.delivery_enabled = True
        kitchen.delivery_fee_paise = 2000
        session.get(MenuListing, seed["listing"]).delivery_enabled = True
        session.commit()
    request = OrderCreate(
        items=[{"menu_listing_id": seed["listing"], "quantity": 2}],
        fulfillment_type="delivery",
    )
    with session_factory() as session:
        user = session.get(User, seed["customer"])
        original = create_order(session, user, request, "delivery-original")
        session.commit()
    assert original.delivery_fee_paise == 2000
    assert original.total_paise == 32000
    with session_factory() as session:
        session.get(Kitchen, seed["kitchen"]).delivery_fee_paise = 5000
        session.commit()
    with session_factory() as session:
        user = session.get(User, seed["customer"])
        detail = get_order(session, user, original.id)
        assert detail.delivery_fee_paise == 2000
        assert detail.total_paise == 32000
        next_order = create_order(session, user, request, "delivery-next")
        assert next_order.delivery_fee_paise == 5000
        assert next_order.total_paise == 35000
        pickup_order = create_order(session, user, payload(seed), "pickup-no-delivery-fee")
        assert pickup_order.delivery_fee_paise == 0
        assert pickup_order.total_paise == 30000
        session.commit()
