import { PlannerForm } from "@/features/planner/PlannerForm";
import { api } from "@/lib/api/client";

export default async function Home() {
  try {
    const activityTypes = await api.activityTypes();
    return <PlannerForm activityTypes={activityTypes} />;
  } catch {
    return <PlannerForm activityTypes={[]} activityTypesUnavailable />;
  }
}
