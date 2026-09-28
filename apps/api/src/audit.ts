import type { Queryable } from "./db.js";

export async function audit(
  db: Queryable,
  actorUserId: string | null,
  action: string,
  entityType: string,
  entityId: string,
  detail: Record<string, unknown> = {},
  requestId?: string,
): Promise<void> {
  await db.query(
    `INSERT INTO audit_events (actor_user_id, action, entity_type, entity_id, detail, request_id) VALUES ($1, $2, $3, $4, $5, $6)`,
    [actorUserId, action, entityType, entityId, JSON.stringify(detail), requestId ?? null],
  );
}
