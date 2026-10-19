declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BUCKET?: R2Bucket;
    DVF_UPLOAD_TOKEN?: string;
  }
}
