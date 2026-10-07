"use client";
import { useAdminFoodKitchen, useAdminFoodDish } from "@/lib/api/generated/admin";
import { ListingForm } from "@/components/organisms/listing-form";
import { QueryState } from "@/components/molecules/query-state";
export function ListingCreatePage({
  id,
  dishId,
  date,
}: {
  id: string;
  dishId?: string;
  date?: string;
}) {
  const kitchen = useAdminFoodKitchen(id);
  const dish = useAdminFoodDish(dishId ?? "", { query: { enabled: !!dishId } });
  if (!kitchen.data || (dishId && !dish.data))
    return (
      <QueryState
        pending={kitchen.isPending || (!!dishId && dish.isPending)}
        error={kitchen.error ?? dish.error}
        retry={() => {
          kitchen.refetch();
          if (dishId) dish.refetch();
        }}
      />
    );
  if (dish.data && dish.data.kitchen_id !== id)
    return <p role="alert">Dish not found in this kitchen.</p>;
  return <ListingForm kitchen={kitchen.data} dish={dishId ? dish.data : undefined} date={date} />;
}
