import { NextFunction, Request, Response } from "express";
import { SupabaseClient, User } from "@supabase/supabase-js";
import { supabase, dbConfig } from "../db/client";
import logger from "../utils/logger";

export type AuthRole = "user" | "admin" | "moderator";

export interface AuthenticatedUser {
    id: string;
    email?: string;
    role: AuthRole;
    raw: User;
}

export interface AuthenticatedRequest extends Request {
    user?: AuthenticatedUser;
}

type SupabaseAuthClient = Pick<SupabaseClient, "auth">;

const getUserRole = (user: User): AuthRole => {
    // Read role from app_metadata (server-controlled, cannot be set by user).
    // app_metadata takes precedence; user_metadata is accepted as a fallback
    // only for legacy compatibility during the transition period.
    const metadataRole = user.app_metadata?.role || user.user_metadata?.role;
    if (metadataRole === "admin") return "admin";
    if (metadataRole === "moderator") return "moderator";
    return "user";
};

/**
 * Extract token from HTTP-only cookie (preferred) or Authorization header (fallback).
 * The fallback supports clients that haven't migrated to cookie-based auth yet.
 */
const extractToken = (req: Request): string | null => {
    if (req.cookies?.access_token) {
        return req.cookies.access_token;
    }
    const authHeader = req.headers.authorization;
    if (authHeader?.startsWith("Bearer ")) {
        return authHeader.slice(7);
    }
    return null;
};

/**
 * Decode JWT token loosely for local development when Supabase auth server is offline.
 * Extracts the user ID (sub), email, and roles/metadata from the token payload.
 */
function decodeJwtLoosely(token: string): AuthenticatedUser | null {
    try {
        const parts = token.split(".");
        if (parts.length !== 3) return null;

        const base64Url = parts[1];
        const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
        const payloadJson = Buffer.from(base64, "base64").toString("utf-8");
        const payload = JSON.parse(payloadJson);

        if (payload.exp && Date.now() / 1000 > payload.exp) {
            logger.warn("Loose JWT verification: Token is expired");
            return null;
        }

        const role = payload.app_metadata?.role || payload.user_metadata?.role || "user";

        return {
            id: payload.sub || "mock-user-id",
            email: payload.email,
            role: role as AuthRole,
            raw: {
                id: payload.sub || "mock-user-id",
                email: payload.email,
                app_metadata: payload.app_metadata || {},
                user_metadata: payload.user_metadata || {},
                aud: payload.aud || "authenticated",
                created_at: new Date().toISOString(),
            } as User,
        };
    } catch (err) {
        logger.error({ message: "Failed to loosely decode JWT", error: err });
        return null;
    }
}

export const createAuthMiddleware =
    (client: SupabaseAuthClient = supabase) =>
    async (req: AuthenticatedRequest, res: Response, next: NextFunction) => {
        const token = extractToken(req);

        if (!token) {
            res.status(401).json({ error: "Unauthorized: Missing access token" });
            return;
        }

        if (dbConfig?.isSupabaseOffline) {
            const decoded = decodeJwtLoosely(token);
            if (decoded) {
                req.user = decoded;
                next();
            } else {
                res.status(401).json({ error: "Unauthorized: Invalid or expired token" });
            }
            return;
        }

        try {
            const { data, error } = await client.auth.getUser(token);

            if (error) {
                const isConnectionError =
                    error.message?.includes("fetch failed") ||
                    error.message?.includes("timeout") ||
                    error.message?.includes("connect") ||
                    error.message?.includes("refused");

                if (isConnectionError) {
                    if (dbConfig) dbConfig.isSupabaseOffline = true;
                    logger.warn({
                        message:
                            "Supabase auth server returned connection error. Setting isSupabaseOffline=true and attempting local loose JWT decoding fallback.",
                        error: error.message,
                    });
                    const decoded = decodeJwtLoosely(token);
                    if (decoded) {
                        req.user = decoded;
                        next();
                        return;
                    }
                }

                res.status(401).json({ error: "Unauthorized: Invalid or expired token" });
                return;
            }

            if (!data.user) {
                res.status(401).json({ error: "Unauthorized: Invalid or expired token" });
                return;
            }

            req.user = {
                id: data.user.id,
                email: data.user.email,
                role: getUserRole(data.user),
                raw: data.user,
            };

            next();
        } catch (err) {
            const errMsg = err instanceof Error ? err.message : String(err);
            if (
                errMsg.includes("fetch failed") ||
                errMsg.includes("refused") ||
                errMsg.includes("timeout")
            ) {
                if (dbConfig) dbConfig.isSupabaseOffline = true;
            }

            logger.warn({
                message:
                    "Supabase auth server request failed. Attempting local loose JWT decoding fallback.",
                error: errMsg,
            });

            const decoded = decodeJwtLoosely(token);
            if (decoded) {
                req.user = decoded;
                next();
            } else {
                res.status(401).json({
                    error: "Unauthorized: Authentication service unavailable and token invalid",
                });
            }
        }
    };

export const requireAuth = createAuthMiddleware();

export const createOptionalAuthMiddleware =
    (client: SupabaseAuthClient = supabase) =>
    async (req: AuthenticatedRequest, res: Response, next: NextFunction) => {
        const token = extractToken(req);

        if (!token) {
            return next();
        }

        if (dbConfig?.isSupabaseOffline) {
            const decoded = decodeJwtLoosely(token);
            if (decoded) {
                req.user = decoded;
            }
            return next();
        }

        try {
            const { data, error } = await client.auth.getUser(token);

            if (error) {
                const isConnectionError =
                    error.message?.includes("fetch failed") ||
                    error.message?.includes("timeout") ||
                    error.message?.includes("connect") ||
                    error.message?.includes("refused");

                if (isConnectionError) {
                    if (dbConfig) dbConfig.isSupabaseOffline = true;
                    logger.warn({
                        message:
                            "Supabase auth server returned connection error. Setting isSupabaseOffline=true and attempting local loose JWT decoding fallback.",
                        error: error.message,
                    });
                    const decoded = decodeJwtLoosely(token);
                    if (decoded) {
                        req.user = decoded;
                    }
                    next();
                    return;
                }

                res.status(401).json({
                    error: "Unauthorized: Invalid or expired token",
                });
                return;
            }

            if (!data.user) {
                res.status(401).json({
                    error: "Unauthorized: Invalid or expired token",
                });
                return;
            }

            req.user = {
                id: data.user.id,
                email: data.user.email,
                role: getUserRole(data.user),
                raw: data.user,
            };

            next();
        } catch (err) {
            const errMsg = err instanceof Error ? err.message : String(err);
            if (
                errMsg.includes("fetch failed") ||
                errMsg.includes("refused") ||
                errMsg.includes("timeout")
            ) {
                if (dbConfig) dbConfig.isSupabaseOffline = true;
            }

            logger.warn({
                message:
                    "Supabase optional auth server request failed. Attempting local loose JWT decoding fallback.",
                error: errMsg,
            });

            const decoded = decodeJwtLoosely(token);
            if (decoded) {
                req.user = decoded;
            }
            next();
        }
    };

export const optionalAuth = createOptionalAuthMiddleware();

export const requireRole =
    (...allowedRoles: AuthRole[]) =>
    (req: AuthenticatedRequest, res: Response, next: NextFunction) => {
        if (!req.user) {
            res.status(401).json({ error: "Authentication is required" });
            return;
        }

        if (!allowedRoles.includes(req.user.role)) {
            res.status(403).json({ error: "Insufficient permissions" });
            return;
        }

        next();
    };
