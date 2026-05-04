-- Defense in depth: enforce that share is in (0, 1] or NULL at the DB layer.
-- Application validation already enforces this; this catches manual SQL or
-- buggy callers that bypass the service layer.

ALTER TABLE "account_owners"
  DROP CONSTRAINT IF EXISTS "account_owners_share_range";
ALTER TABLE "account_owners"
  ADD CONSTRAINT "account_owners_share_range"
  CHECK (share IS NULL OR (share > 0 AND share <= 1));

ALTER TABLE "property_owners"
  DROP CONSTRAINT IF EXISTS "property_owners_share_range";
ALTER TABLE "property_owners"
  ADD CONSTRAINT "property_owners_share_range"
  CHECK (share IS NULL OR (share > 0 AND share <= 1));

ALTER TABLE "vehicle_owners"
  DROP CONSTRAINT IF EXISTS "vehicle_owners_share_range";
ALTER TABLE "vehicle_owners"
  ADD CONSTRAINT "vehicle_owners_share_range"
  CHECK (share IS NULL OR (share > 0 AND share <= 1));
