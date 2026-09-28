-- Session version: embedded in each JWT; bumping it (password change/reset) revokes all existing sessions.
ALTER TABLE users ADD COLUMN session_version integer NOT NULL DEFAULT 0;

-- One-time password-reset tokens. Only the SHA-256 of the token is stored.
CREATE TABLE password_reset_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id),
  token_hash  text NOT NULL UNIQUE,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_by  uuid REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX password_reset_tokens_user_idx ON password_reset_tokens (user_id);
