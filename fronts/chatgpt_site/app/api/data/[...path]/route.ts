import { env } from "cloudflare:workers";

const ROBOTS = "noindex, nofollow, noarchive";

function json(body: unknown, status: number) {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Robots-Tag": ROBOTS,
    },
  });
}

function safeObjectKey(parts: string[]) {
  if (!parts.length || parts.some((part) => part === ".." || part === "." || part.includes("\\"))) {
    return null;
  }
  return `exports/${parts.join("/")}`;
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (!env.BUCKET) return json({ error: "Dataset storage is not configured." }, 503);
  const { path } = await context.params;
  const key = safeObjectKey(path);
  if (!key) return json({ error: "Invalid dataset path." }, 400);

  const object = await env.BUCKET.get(key, { range: request.headers });
  if (!object) return json({ error: "Dataset file not found." }, 404);

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("Accept-Ranges", "bytes");
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public, max-age=300, must-revalidate");
  headers.set("X-Robots-Tag", ROBOTS);
  headers.set("X-Content-Type-Options", "nosniff");
  const range = object.range;
  let status = 200;
  if (range) {
    let start = 0;
    let length = object.size;
    if ("suffix" in range) {
      length = Math.min(object.size, range.suffix);
      start = object.size - length;
    } else {
      if ("offset" in range && typeof range.offset === "number") start = range.offset;
      if ("length" in range && typeof range.length === "number") length = range.length;
      else length = object.size - start;
    }
    const end = Math.min(object.size - 1, start + length - 1);
    headers.set("Content-Range", `bytes ${start}-${end}/${object.size}`);
    headers.set("Content-Length", String(end - start + 1));
    status = 206;
  } else {
    headers.set("Content-Length", String(object.size));
  }
  return new Response(request.method === "HEAD" ? null : object.body, { status, headers });
}

export const HEAD = GET;
