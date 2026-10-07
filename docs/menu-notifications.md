# Menu notifications design

Status: design only. Kitchen follows and their `notify_new_menu` preference are
implemented; publishing does not send follower notifications yet.

## Preference and audience

Following a kitchen is independent of receiving menu alerts. A new follow has
`notify_new_menu: false`; the app can offer an explicit "Notify me about new menus"
toggle. `POST /api/v1/kitchens/{id}/follow` with
`{"notify_new_menu": true}` opts in or updates an existing follow. An omitted body
or empty object preserves an existing preference. Unfollowing removes the
preference. Order status and payment notifications remain independent.

Recipients must have followed and opted in when the menu was published, have an
active account and membership in that kitchen's community, and still follow with
alerts enabled at dispatch. Exclude the publishing user and kitchen operators.
Recheck eligibility immediately before creating an inbox notification and again
before sending push, so pending alerts do not bypass unfollow or opt-out.

## Publication and spam control

Use one menu event per kitchen and service date, with a unique database constraint
on `(kitchen_id, service_date)`. Create the event in the listing transaction when
a listing first becomes published, including creation as published and a
draft-to-published transition. Only an approved, accepting kitchen in an active
community with an orderable listing qualifies. Drafts and ordinary edits do not
create events. Cancel/re-publish must not generate another event for the same day.

Debounce the event for 60 seconds so owners can publish several dishes without
sending one push per dish. The worker reads the eligible published menu at dispatch
and creates at most one notification per follower for that event, protected by a
unique `(user_id, menu_event_id)` constraint. A durable event cursor or recipient
snapshot must ensure that follows created after publication do not receive the
old event. Publication must not perform network calls or synchronous fan-out.

For the first release, only notify for today's service date in Asia/Kolkata.
Future menus remain discoverable but do not generate an alert or a scheduled
morning alert. A suppressed event stays suppressed: editing or resuming a kitchen
does not send a delayed burst of notifications.

At dispatch, suppress the event if the kitchen is paused or suspended, the
community is inactive, or there are no currently orderable listings. Use current
remaining portions, cutoff and eligible fulfillment options, not the original
quantity. Notifications describe a snapshot; checkout remains authoritative.

## Notification storage and payload

The existing `Notification.order_id` is required and the push worker always sends
an order deep link. Do not create fake orders to reuse it. The implementation needs
a migration making `order_id` nullable and adding a menu event reference, with a
constraint requiring the appropriate reference for each notification kind.
Expose nullable `order_id` and the menu reference in the inbox response, and add
kind-specific worker rendering. Retain existing order payloads and delivery rules.

For a single dish, render a title such as "Manisha's Kitchen posted today's menu"
and a body such as "Rajma Chawal · 15 portions available". For multiple dishes,
render a short menu summary and link to the kitchen's dated menu rather than
implying all portions belong to one dish. A menu payload should include:

```json
{
  "kind": "new_menu",
  "kitchen_id": "...",
  "community_id": "...",
  "service_date": "2026-10-08",
  "menu_event_id": "...",
  "notification_id": "..."
}
```

Keep inbox creation transactional and reuse the worker's device ownership,
session eligibility, backoff and invalid-token handling. Push remains at least
once; clients deduplicate by notification ID. Menu alerts must not change order
notification preferences or prevent order lifecycle updates.

## App flow

Follow kitchen → optionally enable menu alerts → owner publishes today's menu →
one batched alert → tap to open the community's dated kitchen menu → checkout.
The kitchen screen uses the existing availability fields to show a pause, even
when the notification was sent before the pause.
