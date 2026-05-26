/**
 * Reverse proxy: browser calls /api-backend/api/... on the Next origin; this route
 * forwards to FastAPI on localhost. Used when NEXT_PUBLIC_API_URL=same-origin so
 * session cookies are set for the dashboard hostname (not a separate API tunnel).
 *
 * A Route Handler is used instead of next.config rewrites so Set-Cookie and
 * request bodies reliably pass through to the client and upstream.
 *
 * ---------------------------------------------------------------------------
 * DO NOT change this file without explicit permission from the project owner.
 * Demo mode depends on correct Set-Cookie forwarding (`demo_session_id` +
 * `arth_demo_fly_instance`). Using Headers.set() for Set-Cookie drops cookies
 * and breaks chat for all visitors on the public demo (multi-machine Fly).
 * ---------------------------------------------------------------------------
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

/** FastAPI from the Next dev server’s perspective (always loopback). */
const UPSTREAM =
  process.env.INTERNAL_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

async function proxy(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const target = `${UPSTREAM}/${path}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (key.toLowerCase() === "host") return;
    headers.set(key, value);
  });

  const method = req.method;
  const hasBody = method !== "GET" && method !== "HEAD";

  const upstreamRes = await fetch(target, {
    method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });

  const outHeaders = new Headers();
  // #region agent log
  const _dbgSetCookies: string[] = [];
  // #endregion
  upstreamRes.headers.forEach((value, key) => {
    if (key.toLowerCase() === "transfer-encoding") return;
    // #region agent log
    if (key.toLowerCase() === "set-cookie") _dbgSetCookies.push(value);
    // #endregion
    // DO NOT use .set() for Set-Cookie — FastAPI sends two cookies; .set() keeps only the last.
    if (key.toLowerCase() === "set-cookie") {
      outHeaders.append(key, value);
    } else {
      outHeaders.set(key, value);
    }
  });
  // #region agent log
  const _dbgOutSetCookie = outHeaders.get("set-cookie");
  if (_dbgSetCookies.length > 0) {
    console.log(`[DEBUG-13c44f] ${JSON.stringify({sessionId:'13c44f',location:'route.ts:proxy',hypothesisId:'H2',message:'proxy_set_cookie_handling',data:{path,upstreamSetCookieCount:_dbgSetCookies.length,upstreamSetCookies:_dbgSetCookies.map(c=>c.substring(0,60)),outHeaderSetCookie:_dbgOutSetCookie?.substring(0,80),upstreamStatus:upstreamRes.status},timestamp:Date.now()})}`);
  }
  // #endregion

  return new NextResponse(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function PUT(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
