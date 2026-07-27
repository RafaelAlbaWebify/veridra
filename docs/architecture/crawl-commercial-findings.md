# Commercial crawl findings

## Purpose

This milestone expands Veridra's existing bounded same-origin crawl with page-level evidence expected in professional agency audits. It does not replace or broaden the crawler's network safety boundary.

## Existing foundation retained

- same-origin HTTP/HTTPS pages only;
- sequential bounded collection;
- explicit page, depth, sitemap, response-byte and total-byte limits;
- public-target validation and redirect revalidation for every collected page;
- no authentication, script execution, form submission or private-network access;
- deterministic affected-URL evidence.

## New findings

### Duplicate metadata

Non-empty document titles and non-empty meta descriptions are normalized for comparison. A duplicate finding is emitted only when the same normalized value appears on more than one crawled page. Empty or missing values remain covered by existing missing-field findings.

Evidence contains the normalized value and a bounded, sorted URL list for every duplicate group.

### Missing image alternative text

Every image without an `alt` attribute is counted per page. An explicit empty `alt=""` is treated as present because it may intentionally mark a decorative image. Evidence contains affected URLs and missing-alt counts.

### Redirect chains

A redirect-chain finding is emitted when collected page evidence contains more than one redirect hop. Evidence contains requested URL, final URL and the bounded redirect chain already produced by the collector.

### Oversized HTML

Page size is derived only from collected HTML body bytes. It is not described as browser transfer size, compressed size or total page weight. A deterministic threshold is used and reported in evidence.

## Evidence constraints

All lists and groups are sorted deterministically. Evidence remains bounded by the crawl limits and does not duplicate full HTML bodies.

## Explicit exclusions

- JavaScript-rendered DOM inspection;
- image file-size collection;
- CSS, JavaScript or total-page transfer weight;
- cross-origin resource crawling;
- semantic duplicate-content analysis;
- backlink or keyword databases.

Related to issue #56.
