import { randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { SignJWT, jwtVerify } from "jose";
import type { FastifyRequest } from "fastify";
import { HttpError } from "./errors.js";

const scrypt = promisify(scryptCb) as (password: string, salt: Buffer, keylen: number) => Promise<Buffer>;

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const key = await scrypt(password, salt, 64);
  return `scrypt$${salt.toString("base64")}$${key.toString("base64")}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [scheme, saltB64, keyB64] = stored.split("$");
  if (scheme !== "scrypt" || !saltB64 || !keyB64) return false;
  const expected = Buffer.from(keyB64, "base64");
  const actual = await scrypt(password, Buffer.from(saltB64, "base64"), expected.length);
  return timingSafeEqual(expected, actual);
}

export interface AuthUser {
  id: string;
  email: string;
  role: "collector" | "valuer" | "admin";
}

export class TokenService {
  private readonly key: Uint8Array;
  constructor(secret: string) {
    this.key = new TextEncoder().encode(secret);
  }

  sign(user: AuthUser): Promise<string> {
    return new SignJWT({ email: user.email, role: user.role })
      .setProtectedHeader({ alg: "HS256" })
      .setSubject(user.id)
      .setIssuedAt()
      .setExpirationTime("12h")
      .sign(this.key);
  }

  async verify(token: string): Promise<AuthUser> {
    const { payload } = await jwtVerify(token, this.key, { algorithms: ["HS256"] });
    return { id: String(payload.sub), email: String(payload.email), role: payload.role as AuthUser["role"] };
  }
}

declare module "fastify" {
  interface FastifyRequest {
    user?: AuthUser;
  }
}

export function requireUser(req: FastifyRequest): AuthUser {
  if (!req.user) throw new HttpError(401, "Authentication required", "unauthorized");
  return req.user;
}

export function requireRole(req: FastifyRequest, ...roles: AuthUser["role"][]): AuthUser {
  const u = requireUser(req);
  if (!roles.includes(u.role)) throw new HttpError(403, `Requires role: ${roles.join(" or ")}`, "forbidden");
  return u;
}
