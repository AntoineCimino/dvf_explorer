# Data hosting spike results

Updated: 2026-10-19

## GitHub Release assets

Tested with a temporary 423-byte synthetic Parquet file containing no DVF
records. The temporary release and tag were deleted after the check.

| Assumption | Result | Evidence |
| --- | --- | --- |
| HTTP byte ranges | Pass | A ranged GET returned `206 Partial Content`, `Accept-Ranges: bytes`, and the requested 16-byte range. |
| Browser cross-origin fetch | Fail | The final asset response did not include `Access-Control-Allow-Origin` for the supplied browser origin. DuckDB-WASM cannot read the asset cross-origin. |
| Data search indexing controls | Fail | The asset response did not supply a `X-Robots-Tag` policy that this project can manage. |

**Decision:** Do not publish DVF assets as GitHub Releases. Use a Site Worker
bound to R2, serving files on the Site origin with explicit range handling,
`X-Robots-Tag: noindex, nofollow, noarchive`, and crawler restrictions. The
worker must support read-only public object access and an authenticated upload
path for refresh jobs. Validate the final headers and a real browser query
before uploading transaction-level data.

## Front availability

- Claude artifact: not tested; no artifact front exists yet.
- ChatGPT Site: not tested; the working explorer front remains to be built.

The temporary release test validated only HTTP range behavior. It did not
validate DuckDB-WASM in either front.
