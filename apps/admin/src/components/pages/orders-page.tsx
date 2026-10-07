"use client";
import Link from "next/link";
import { useState } from "react";
import { useAdminOrdersList } from "@/lib/api/generated/admin";
import {
  AdminOrdersListStatus,
  type AdminOrdersListPaymentStatus,
} from "@/lib/api/generated/models";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { CommunityFilter } from "@/components/molecules/community-filter";
import { useListControls } from "@/lib/use-list-controls";
import { money, dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { Combobox } from "@/components/molecules/combobox";
import { availableOrderActions } from "@/lib/order-actions";
import { FormLink } from "@/components/molecules/form-link";
import { DataTable } from "@/components/organisms/data-table";
export function OrdersPage({
  initialStatus = "",
  initialCommunity = "",
  customerId,
  kitchenId,
}: {
  initialStatus?: AdminOrdersListStatus | "";
  initialCommunity?: string;
  customerId?: string;
  kitchenId?: string;
}) {
  const controls = useListControls();
  const [community, setCommunity] = useState(initialCommunity);
  const [customer, setCustomer] = useState(customerId ?? "");
  const [kitchen, setKitchen] = useState(kitchenId ?? "");
  const [status, setStatus] = useState(initialStatus);
  const [payment, setPayment] = useState<AdminOrdersListPaymentStatus | "">("");
  const query = useAdminOrdersList(
    {
      ...controls.params,
      customer_id: customer || undefined,
      kitchen_id: kitchen || undefined,
      status: status || undefined,
      community_id: community || undefined,
      payment_status: payment || undefined,
      sort: "-created_at",
    },
    { query: { refetchInterval: 30000 } },
  );
  return (
    <>
      <PageHeading
        title="Orders"
        description="Search by order number, customer, or kitchen."
        action={<FormLink href="/orders/new">New order</FormLink>}
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={community}
          onChange={(value) => {
            setCommunity(value);
            controls.setOffset(0);
          }}
        />
        <ReferencePicker
          kind="user"
          name="user_filter"
          required={false}
          emptyLabel="All users"
          label="Customer filter"
          inline
          value={customer}
          onChange={(value) => {
            setCustomer(value);
            controls.setOffset(0);
          }}
        />
        <ReferencePicker
          kind="kitchen"
          name="kitchen_filter"
          required={false}
          emptyLabel="All kitchens"
          approvedKitchensOnly={false}
          label="Kitchen filter"
          inline
          value={kitchen}
          onChange={(value) => {
            setKitchen(value);
            controls.setOffset(0);
          }}
        />
        <Combobox
          label="Order status"
          aria-label="Order status"
          className="w-auto"
          value={status ?? ""}
          onValueChange={(value) => {
            setStatus(value as AdminOrdersListStatus | "");
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All statuses" },
            ...Object.values(AdminOrdersListStatus).map((value) => ({
              value,
              label: value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()),
            })),
          ]}
        />
        <Combobox
          label="Payment status"
          aria-label="Payment status"
          className="w-auto"
          value={payment ?? ""}
          onValueChange={(value) => {
            setPayment(value as AdminOrdersListPaymentStatus | "");
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All payment states" },
            { value: "unpaid", label: "Unpaid" },
            { value: "customer_reported", label: "Customer reported" },
            { value: "kitchen_confirmed", label: "Kitchen confirmed" },
          ]}
        />
      </ListToolbar>
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
      {query.data && (
        <>
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "number",
                title: "Order",
                render: (row) => (
                  <Link className="font-medium hover:underline" href={`/orders/${row.id}`}>
                    #{row.order_number}
                  </Link>
                ),
              },
              {
                key: "kitchen",
                title: "Kitchen",
                render: (row) => (
                  <Link className="hover:underline" href={`/kitchens/${row.kitchen_id}`}>
                    {row.kitchen_name}
                  </Link>
                ),
              },
              {
                key: "customer",
                title: "Customer",
                render: (row) => (
                  <Link href={`/users/${row.customer_id}`} className="hover:underline">
                    {row.customer_name}
                  </Link>
                ),
              },
              {
                key: "status",
                title: "Status",
                render: (row) => <StatusBadge value={row.status} />,
              },
              {
                key: "payment",
                title: "Payment",
                render: (row) => <StatusBadge value={row.payment_status} />,
              },
              {
                key: "total",
                title: "Total",
                render: (row) => money(row.total_paise),
              },
              {
                key: "actions",
                title: "Actions",
                render: (row) =>
                  availableOrderActions(row).length ? (
                    <FormLink href={`/orders/${row.id}/edit`}>Edit</FormLink>
                  ) : (
                    <FormLink href={`/orders/${row.id}`}>View</FormLink>
                  ),
              },
              {
                key: "created",
                title: "Placed",
                render: (row) => dateTime(row.created_at),
              },
            ]}
          />
          <Pagination
            total={query.data.total}
            offset={controls.offset}
            onPage={controls.setOffset}
          />
        </>
      )}
    </>
  );
}
