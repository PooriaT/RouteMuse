export type BoundingBox = {
  south: number;
  west: number;
  north: number;
  east: number;
};

export type PlanningArea = {
  latitude: number;
  longitude: number;
  display_name: string;
  bounding_box: BoundingBox | null;
  source_provider: string;
  source_attribution: string;
};
