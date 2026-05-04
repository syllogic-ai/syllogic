-- Backfill: create one 'self' person per existing user, and 100%-share
-- ownership rows for every existing account, property, and vehicle.
-- Idempotent so it can be re-run safely (e.g. on baselined deploys).

INSERT INTO people (id, user_id, name, kind, created_at, updated_at)
SELECT gen_random_uuid(), u.id, COALESCE(NULLIF(u.name, ''), 'You'), 'self', NOW(), NOW()
FROM users u
WHERE NOT EXISTS (
  SELECT 1 FROM people p WHERE p.user_id = u.id AND p.kind = 'self'
);

INSERT INTO account_owners (account_id, person_id, share, created_at)
SELECT a.id, p.id, NULL, NOW()
FROM accounts a
JOIN people p ON p.user_id = a.user_id AND p.kind = 'self'
ON CONFLICT (account_id, person_id) DO NOTHING;

INSERT INTO property_owners (property_id, person_id, share, created_at)
SELECT pr.id, p.id, NULL, NOW()
FROM properties pr
JOIN people p ON p.user_id = pr.user_id AND p.kind = 'self'
ON CONFLICT (property_id, person_id) DO NOTHING;

INSERT INTO vehicle_owners (vehicle_id, person_id, share, created_at)
SELECT v.id, p.id, NULL, NOW()
FROM vehicles v
JOIN people p ON p.user_id = v.user_id AND p.kind = 'self'
ON CONFLICT (vehicle_id, person_id) DO NOTHING;
