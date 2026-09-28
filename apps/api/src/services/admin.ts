import type { Queryable } from "../db.js";
import { audit } from "../audit.js";

/**
 * Promote an existing, already-registered account to admin. Operator-only: run on the server via
 * `npm run create-admin -- <email>`. There is deliberately no web or email-based bootstrap, because
 * email addresses are not verified at registration.
 */
export async function promoteToAdmin(db: Queryable, email: string): Promise<{ id: string; email: string } | null> {
  const res = await db.query<{ id: string; email: string }>(
    `UPDATE users SET role = 'admin' WHERE email = $1 RETURNING id, email`,
    [email.trim().toLowerCase()],
  );
  const row = res.rows[0] ?? null;
  if (row) await audit(db, null, "user.promoted_to_admin_by_operator", "user", row.id, { email: row.email });
  return row;
}
