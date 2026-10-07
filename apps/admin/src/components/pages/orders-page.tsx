"use client";
import Link from "next/link";
import { useState } from "react";
import { useAdminOrdersList } from "@/lib/api/generated/admin";
import {
  AdminOrdersListStatus,
  type AdminOrdersListPaymentStatus,
} from "@/lib/api/generated/models";
import { CommunityFilter } from "@/components/molecules/community-filter";
import { useListControls } from "@/lib/use-list-controls";
import { money, dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { Select } from "@/components/atoms/select";
import { DataTable } from "@/components/organisms/data-table";
export function OrdersPage({ initialStatus = "" }: { initialStatus?: AdminOrdersListStatus | "" }) {
  const controls = useListControls();
  const [community, setCommunity] = useState("");
  const [status, setStatus] = useState(initialStatus);
  const [payment, setPayment] = useState<AdminOrdersListPaymentStatus | "">("");
  const query = useAdminOrdersList(
    {
      ...controls.params,
      status: status || undefined,
      community_id: community || undefined,
      payment_status: payment || undefined,
      sort: "-created_at",
    },
    { query: { refetchInterval: 30000 } },
  );
  return (
    <>
      <PageHeading title="Orders" description="Search by order number, customer, or kitchen." />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={community}
          onChange={(value) => {
            setCommunity(value);
            controls.setOffset(0);
          }}
        />
        <Select
          aria-label="Order status"
          className="w-auto"
          value={status ?? ""}
          onChange={(event) => {
            setStatus(event.target.value as AdminOrdersListStatus | "");
            controls.setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          {Object.values(AdminOrdersListStatus).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Payment status"
          className="w-auto"
          value={payment ?? ""}
          onChange={(event) => {
            setPayment(event.target.value as AdminOrdersListPaymentStatus | "");
            controls.setOffset(0);
          }}
        >
          <option value="">All payment states</option>
          <option value="unpaid">Unpaid</option>
          <option value="customer_reported">Customer reported</option>
          <option value="kitchen_confirmed">Kitchen confirmed</option>
        </Select>
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
                render: (row) => row.customer_name,
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
