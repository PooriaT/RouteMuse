import { PlannerForm } from "@/features/planner/PlannerForm";
import { api } from "@/lib/api/client";
export default async function Home() {
  const activityTypes = await api.activityTypes();
  return <PlannerForm activityTypes={activityTypes}/>;
}
