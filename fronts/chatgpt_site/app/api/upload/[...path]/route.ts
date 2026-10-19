import { env } from "cloudflare:workers";

const ROBOTS = "noindex, nofollow, noarchive";

function json(body: unknown, status: number) {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store", "X-Robots-Tag": ROBOTS },
  });
}

export async function PUT(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (!env.BUCKET || !env.DVF_UPLOAD_TOKEN) {
    return json({ error: "Upload service is not configured." }, 503);
  }
  const authorization = request.headers.get("authorization") ?? "";
  if (authorization !== `Bearer ${env.DVF_UPLOAD_TOKEN}`) {
    return json({ error: "Unauthorized." }, 401);
  }
  const { path } = await context.params;
  if (!path.length || path.some((part) => !/^[a-zA-Z0-9._=-]+$/.test(part) || part === "..")) {
    return json({ error: "Invalid export path." }, 400);
  }
  if (!request.body) return json({ error: "Request body is required." }, 400);
  const contentEncoding = request.headers.get("content-encoding");
  if (contentEncoding && contentEncoding !== "gzip") {
    return json({ error: "Unsupported content encoding." }, 400);
  }

  const key = `exports/${path.join("/")}`;
  const contentType = request.headers.get("content-type") || "application/octet-stream";
  const object = await env.BUCKET.put(key, request.body, {
    httpMetadata: {
      contentType,
      ...(contentEncoding ? { contentEncoding } : {}),
      cacheControl: "public, max-age=300, must-revalidate",
    },
  });
  return json({ key: object.key, size: object.size, etag: object.httpEtag }, 201);
}
