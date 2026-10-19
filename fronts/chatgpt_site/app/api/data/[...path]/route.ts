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

  const rangeHeader = request.headers.get("range");
  const rangeMatch = rangeHeader?.match(/^bytes=(\d*)-(\d*)$/);
  let requestedRange: { offset: number; length?: number } | { suffix: number } | undefined;
  if (rangeMatch) {
    const [, rawStart, rawEnd] = rangeMatch;
    if (!rawStart && rawEnd) {
      const suffix = Number(rawEnd);
      if (Number.isSafeInteger(suffix) && suffix > 0) requestedRange = { suffix };
    } else if (rawStart) {
      const offset = Number(rawStart);
      const end = rawEnd ? Number(rawEnd) : undefined;
      if (Number.isSafeInteger(offset) && offset >= 0 &&
          (end === undefined || (Number.isSafeInteger(end) && end >= offset))) {
        requestedRange = { offset, ...(end === undefined ? {} : { length: end - offset + 1 }) };
      }
    }
  }
  const object = await env.BUCKET.get(key, requestedRange ? { range: requestedRange } : undefined);
  if (!object) return json({ error: "Dataset file not found." }, 404);

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  if (path.at(-1)?.endsWith(".json.gz")) headers.set("Content-Encoding", "gzip");
  headers.set("Accept-Ranges", "bytes");
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public, max-age=300, must-revalidate");
  headers.set("X-Robots-Tag", ROBOTS);
  headers.set("X-Content-Type-Options", "nosniff");
  let status = 200;
  if (requestedRange) {
    let start = 0;
    let length = object.size;
    if ("suffix" in requestedRange) {
      length = Math.min(object.size, requestedRange.suffix);
      start = object.size - length;
    } else {
      start = requestedRange.offset;
      length = requestedRange.length ?? (object.size - start);
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
