# Quality Runner map schema

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `type` | `cluster`, `object`, `source-layer`, `support-layer`, `unknown` | Catalog noun kind |
| `universe` | `live`, `leftover`, `ghost`, `unknown` | Whether the source is in force |
| `status` | `stub`, `verified`, `stale` | Citation/freshness state |
| `access_tier` | `public`, `private`, `owner-only`, `unknown` | Distribution boundary |

Evidence and certification cards must cite their owning contract or source;
they must not claim that a receipt proves behavior outside its declared scope.

