# GOG API Research Notes

Research spike for TASK-0019. Documents the GOG authentication flow, library
endpoint, download metadata endpoint, and download URL retrieval well enough to
implement TASK-0004 (auth) and TASK-0005 (refresh/parser).

**Status of this document:** All endpoints documented here are unofficial and
reverse-engineered. They have been stable since roughly 2015 and are used by
multiple active open-source projects (see Sources), but GOG may change them
without notice.

---

## Sources

- **Minigalaxy** (Python GOG client): `github.com/sharkwouter/minigalaxy` —
  `minigalaxy/api.py` is the primary Python reference.
- **lgogdownloader** (C++ GOG downloader): `github.com/Sude-/lgogdownloader` —
  `src/galaxyapi.cpp` and `src/downloader.cpp` for download URL flow.
- **Unofficial GOG API docs**: `gogapidocs.readthedocs.io` — community
  documentation cross-referenced against the source implementations above.

Do not copy code from these projects. Use them to understand the API surface
and cross-check findings.

---

## 1. Authentication

### 1.1 OAuth Credentials

These credentials are used by the GOG Galaxy desktop client and by every
known open-source GOG downloader. They are effectively public.

```
client_id:     46899977096215655
client_secret: 9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9
redirect_uri:  https://embed.gog.com/on_login_success?origin=client
```

These values are hardcoded in lgogdownloader, Minigalaxy, Heroic Games
Launcher, and others. They represent the "Galaxy client" OAuth application on
GOG's auth server.

**Risk:** GOG could rotate these credentials, but has not done so in 10+ years.
Monitor lgogdownloader issues for any breakage signals.

### 1.2 Login URL Construction

Send the user to a browser with this URL:

```
https://auth.gog.com/auth
  ?client_id=46899977096215655
  &redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient
  &response_type=code
  &layout=client2
```

The `layout=client2` parameter renders the login page without the full GOG
website chrome, suitable for an embedded webview or browser popup.

After successful login, the browser is redirected to:

```
https://embed.gog.com/on_login_success?origin=client&code=<authorization_code>
```

The `code` query parameter is the authorization code to exchange for tokens.
For a CLI, the options are:
- Open a browser and capture the redirect via a localhost callback server.
- Print the login URL and ask the user to paste the redirect URL or just the
  `code` value (headless/SSH fallback).

### 1.3 Token Exchange

**Endpoint:** `GET https://auth.gog.com/token`

Exchange an authorization code for access and refresh tokens:

```
GET https://auth.gog.com/token
  ?client_id=46899977096215655
  &client_secret=9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9
  &grant_type=authorization_code
  &code=<authorization_code>
  &redirect_uri=https://embed.gog.com/on_login_success?origin=client
```

**Note:** lgogdownloader and Minigalaxy both use GET with query parameters
rather than a POST body. This is non-standard OAuth but is what GOG's server
expects.

**Response (200 OK):**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "eyJ...",
  "user_id": "12345678901234567",
  "session_id": "987654321",
  "scope": ""
}
```

- `access_token`: short-lived (~1 hour), used as `Authorization: Bearer <token>`
- `refresh_token`: long-lived, used to obtain new access tokens without re-login
- `expires_in`: seconds until `access_token` expires
- `user_id`: stable account identifier, safe to store as a non-secret discriminator

### 1.4 Token Refresh

**Endpoint:** `GET https://auth.gog.com/token`

Exchange a refresh token for a new access token:

```
GET https://auth.gog.com/token
  ?client_id=46899977096215655
  &client_secret=9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9
  &grant_type=refresh_token
  &refresh_token=<refresh_token>
```

**Response:** Same shape as token exchange. A new `refresh_token` is also
returned; replace the stored one.

### 1.5 Making Authenticated Requests

All endpoints below require:

```
Authorization: Bearer <access_token>
```

Refresh proactively before the token expires (`expires_in` seconds after
issue). Store the expiry timestamp alongside the non-secret session metadata.
Never store the `access_token` or `refresh_token` in plain files unless
explicitly documented as an approved fallback (see TASK-0004).

---

## 2. User Info

**Endpoint:** `GET https://embed.gog.com/userData.json`
**Auth:** Bearer token required
**Stability:** Long-term stable (used by lgogdownloader since ~2014)

**Sanitized response shape:**

```json
{
  "country": "US",
  "currencies": [...],
  "selectedCurrency": {"code": "USD", "symbol": "$"},
  "preferredLanguage": {"code": "en", "name": "English"},
  "ratingBrand": "ESRB",
  "isLoggedIn": true,
  "checksum": {"cart": null, "games": "abc123", "wishlist": null, "reviews_votes": null, "games_rating": null},
  "updates": {"messages": 0, "pendingFriendRequests": 0, "unreadChatMessages": 0, "products": 0, "total": 0},
  "userId": "12345678901234567",
  "username": "your_username",
  "galaxyUserId": "12345678901234567",
  "email": "REDACTED",
  "avatar": "https://images.gog.com/...",
  "walletBalance": {"currency": "USD", "amount": 0},
  "totalCredit": {"currency": "USD", "amount": 0},
  "personalizedProductPrices": [],
  "personalizedSeriesPrices": []
}
```

Useful fields for gog-cli: `userId`, `username`. Store `userId` as a
non-secret account discriminator in session metadata. Never log `email`.

---

## 3. Owned Games Library

Two endpoints cover library discovery. Use both.

### 3.1 Quick Product ID List

**Endpoint:** `GET https://embed.gog.com/user/data/games`
**Auth:** Bearer token required
**Stability:** Long-term stable

**Response:**

```json
{
  "owned": [1234567890, 9876543210, 1111111111]
}
```

Returns only product IDs with no pagination. Fast and useful for checking
whether a product ID is owned, but contains no metadata.

### 3.2 Paginated Library with Metadata

**Endpoint:** `GET https://embed.gog.com/account/getFilteredProducts`
**Auth:** Bearer token required
**Stability:** Long-term stable; used by Minigalaxy, lgogdownloader, Heroic

**Query parameters:**

| Parameter | Type | Notes |
|-----------|------|-------|
| `mediaType` | int | `1` = games, `2` = movies. Always use `1`. |
| `page` | int | 1-based page number. Default: 1. |
| `search` | string | Optional title filter. |
| `sortBy` | string | e.g. `title`. Optional. |
| `system` | string | `gog` (default), `windows`, `osx`, `linux`. Optional. |
| `language` | string | e.g. `en`. Optional. |

Typical request: `?mediaType=1&page=1`

**Sanitized response shape:**

```json
{
  "sortBy": "title",
  "page": 1,
  "totalProducts": 42,
  "totalPages": 1,
  "productsPerPage": 100,
  "products": [
    {
      "id": 1234567890,
      "title": "Example Game",
      "slug": "example_game",
      "image": "//images-2.gog.com/abc123",
      "url": "/game/example_game",
      "worksOn": {
        "Windows": true,
        "Mac": false,
        "Linux": true
      },
      "category": "Action",
      "rating": 42,
      "isComingSoon": false,
      "isMovie": false,
      "isGame": true,
      "price": {...},
      "isDiscounted": false
    }
  ],
  "tags": [],
  "appliedFilters": {}
}
```

**Pagination:** Iterate `page` from `1` to `totalPages`. With `productsPerPage`
at 100, most libraries fit in one page. Always check `totalPages`.

**Key fields for gog-cli:**
- `id` — stable GOG product identifier
- `title` — display title
- `slug` — URL-safe name, useful as directory name (sanitize before use)
- `worksOn` — platform availability

---

## 4. Per-Game Download Metadata

### 4.1 Product Info Endpoint

**Endpoint:** `GET https://api.gog.com/products/{product_id}`
**Auth:** Bearer token required
**Stability:** Long-term stable; primary download metadata source

**Query parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| `expand` | `downloads,expanded_dlcs,description,screenshots,videos,related_products,changelog` | Include downloads. At minimum, include `downloads`. |
| `locale` | `en-US` | Optional. Affects localized strings. |

**Sanitized response shape (focused on download-relevant fields):**

```json
{
  "id": 1234567890,
  "title": "Example Game",
  "slug": "example_game",
  "downloads": {
    "installers": [
      {
        "id": "installer_windows_en",
        "name": "Example Game (Windows) (en)",
        "os": "windows",
        "language": "en",
        "language_full": "English",
        "version": "1.2.3",
        "total_size": 4294967296,
        "files": [
          {
            "id": "en1installer1",
            "size": 4294967296,
            "downlink": "https://api.gog.com/products/1234567890/downlink/installer/en1installer1"
          }
        ]
      },
      {
        "id": "installer_linux_en",
        "name": "Example Game (Linux) (en)",
        "os": "linux",
        "language": "en",
        "language_full": "English",
        "version": "1.2.3",
        "total_size": 3758096384,
        "files": [
          {
            "id": "en2installer1",
            "size": 3758096384,
            "downlink": "https://api.gog.com/products/1234567890/downlink/installer/en2installer1"
          }
        ]
      }
    ],
    "patches": [
      {
        "id": "patch_windows_en_1_2_3",
        "name": "Patch 1.2.3 (Windows) (en)",
        "os": "windows",
        "language": "en",
        "version": "1.2.3",
        "files": [
          {
            "id": "en1patch1",
            "size": 104857600,
            "downlink": "https://api.gog.com/products/1234567890/downlink/patch/en1patch1"
          }
        ]
      }
    ],
    "language_packs": [],
    "bonus_content": [
      {
        "id": 123,
        "name": "Soundtrack",
        "type": "soundtrack",
        "count": 1,
        "total_size": 157286400,
        "files": [
          {
            "id": "bonus1",
            "size": 157286400,
            "downlink": "https://api.gog.com/products/1234567890/downlink/bonus_content/bonus1"
          }
        ]
      }
    ]
  },
  "expanded_dlcs": []
}
```

**Mapping to gog-cli file roles:**

| GOG field | gog-cli role |
|-----------|-------------|
| `downloads.installers[]` | `installer` |
| `downloads.patches[]` | `patch` |
| `downloads.language_packs[]` | `language_pack` |
| `downloads.bonus_content[]` | `extra` |
| DLC installers | `installer` (scoped to DLC product_id) |

**Key fields per file entry:**
- `id` — stable source file identifier within this product; use as `source_id`
- `os` — `windows`, `osx`, `linux`
- `language` — ISO 639-1 code (e.g. `en`, `fr`, `de`)
- `version` — installer version string (not always present on extras)
- `total_size` — expected total size in bytes
- `files[].downlink` — URL to call for the actual CDN download link (see §5)

### 4.2 Batch Product Info

**Endpoint:** `GET https://api.gog.com/products`
**Auth:** Bearer token required

Accepts `ids=1234567890,9876543210` (comma-separated, up to 50). Returns an
array of product objects with the same shape as the single-product endpoint.
Useful for bulk prefetching during refresh.

---

## 5. Download URL Retrieval

Download URLs are **two-step** and **short-lived**. The `downlink` field in
the product info response is not a CDN URL — it is a GOG API endpoint that
returns a time-limited signed CDN URL.

### Step 1: Resolve the downlink

**Endpoint:** `GET <downlink_url>` (value from `files[].downlink`)
**Auth:** Bearer token required
**Example:** `GET https://api.gog.com/products/1234567890/downlink/installer/en1installer1`

**Response:**

```json
{
  "downlink": "https://gog-cdn-fastly.gog.com/example_game/installer_en_1_2_3.exe?_token=abc123&expires=1234567890&...",
  "checksum": "https://cdn.gog.com/example_game/installer_en_1_2_3.exe.xml?...",
}
```

- `downlink` — the actual signed CDN URL to download. **Short-lived** (minutes
  to hours). Do not cache this URL between sessions. Fetch it immediately
  before starting the download.
- `checksum` — URL to an XML file containing MD5 hash and chunk-level integrity
  data (see §6).

### Step 2: Download from the CDN URL

Stream the file from `downlink`. The CDN supports HTTP range requests
(`Range: bytes=N-`) for resumable downloads; test for a `206 Partial Content`
response before assuming resume is safe.

**Important implementation notes:**
- Fetch the downlink URL immediately before starting each download. Do not
  store signed CDN URLs in the manifest or cache — they expire and may contain
  account-identifying parameters.
- If the access token expires during a long download, only the downlink
  resolution step needs a fresh token; the CDN URL itself is independently
  signed.
- Re-resolve the downlink URL on resume or retry rather than reusing a stored
  CDN URL.

---

## 6. Checksum Verification

The `checksum` URL from §5 points to an XML file:

```xml
<file name="installer_en_1_2_3.exe" available="1" notavailablemsg=""
      md5="d41d8cd98f00b204e9800998ecf8427e"
      chunks="1" timestamp="1234567890"
      total_size="4294967296">
  <chunk method="md5" from="0" to="4294967295">
    d41d8cd98f00b204e9800998ecf8427e
  </chunk>
</file>
```

Key attributes:
- `md5` — MD5 of the complete file
- `total_size` — expected file size in bytes
- `chunks` — number of chunks (for parallel/segmented downloads)
- `chunk[@from]`, `chunk[@to]`, `chunk[text]` — byte range and MD5 per chunk

For gog-cli's initial implementation: verify `total_size` and the top-level
`md5`. Chunk-level verification can be added later.

Note: not all files have a checksum URL. `bonus_content` files sometimes omit
it. Treat a missing or empty `checksum` field as "verification limited to size."

---

## 7. Endpoint Reference Table

| Endpoint | Host | Auth | Purpose | Stability |
|----------|------|------|---------|-----------|
| `GET /auth` | auth.gog.com | None | Browser login page | Stable (unofficial) |
| `GET /token` | auth.gog.com | None | Token exchange and refresh | Stable (unofficial) |
| `GET /userData.json` | embed.gog.com | Bearer | User info (username, userId) | Stable (unofficial) |
| `GET /user/data/games` | embed.gog.com | Bearer | All owned product IDs | Stable (unofficial) |
| `GET /account/getFilteredProducts` | embed.gog.com | Bearer | Paginated library with metadata | Stable (unofficial) |
| `GET /account/gameDetails/{id}.json` | embed.gog.com | Bearer | Per-game download list (older API) | Stable (unofficial) |
| `GET /products/{id}` | api.gog.com | Bearer | Product info + download metadata | Stable (unofficial) |
| `GET /products` | api.gog.com | Bearer | Batch product info (up to 50 IDs) | Stable (unofficial) |
| `GET /products/{id}/downlink/{type}/{file_id}` | api.gog.com | Bearer | Resolve signed CDN download URL | Stable (unofficial) |
| `GET /<checksum_path>.xml` | cdn.gog.com | None | Checksum XML (MD5 + chunks) | Stable (unofficial) |

All endpoints are **unofficial and reverse-engineered**. None are formally
documented by GOG for third-party use.

---

## 8. Galaxy Content System (Out of Scope for Now)

lgogdownloader also uses a "Galaxy" content-system API for delta/incremental
updates:

- `GET https://content-system.gog.com/products/{id}/os/{platform}/builds?generation=2`
- `GET https://cdn.gog.com/content-system/v1/manifests/{id}/{platform}/{build_id}/repository.json`
- `GET https://content-system.gog.com/products/{id}/secure_link?generation=2&path={path}`

This system enables file-level delta updates and parallel chunk downloads, but
is significantly more complex than the installer-based approach. It is out of
scope for gog-cli's initial implementation.

**Recommendation:** Implement the installer-based flow (§3–§6) first. The
Galaxy content system can be added later as an optional fast-sync path.

---

## 9. Known Instability and Breakage History

- **Auth endpoint structure** has been stable since at least 2015. No breaking
  changes observed in lgogdownloader issue history during that period.
- **`embed.gog.com` library endpoints** occasionally return unexpected shapes
  when GOG deploys website changes. lgogdownloader issue #123 shows an example
  of a login failure when the site changed. The parser should fail clearly and
  tell the user to file a bug rather than silently returning empty results.
- **Token endpoint uses GET** (not POST). This is non-standard OAuth 2.0 but
  has remained consistent. If GOG ever enforces POST, token exchange will
  break with a 405.
- **`api.gog.com/products`** is more API-like and has been more stable than
  `embed.gog.com` endpoints, which are tied to the website.
- **CDN URL format** changes periodically (different CDN providers, different
  signing schemes), but because CDN URLs are never stored by gog-cli, this
  only matters at download time. Re-resolving the downlink URL before each
  download is the correct mitigation.
- **`bonus_content` type field**: values like `"soundtrack"`, `"artbook"`,
  `"wallpaper"` are inconsistent. Do not rely on the type string for anything
  beyond display. Map all `bonus_content` to the `extra` role.

---

## 10. Recommended Approach for gog-cli

### Auth (TASK-0004)

1. Use the known `client_id` / `client_secret` / `redirect_uri`.
2. Construct the login URL and open it in a browser (or print it for headless use).
3. Accept the redirect URL or bare `code` from the user as a paste fallback.
4. Exchange the code for tokens via `GET https://auth.gog.com/token`.
5. Store `refresh_token` in OS keyring; store `expires_in` + issue time and
   `user_id` in non-secret session state.
6. Refresh the access token automatically when `expires_in` has elapsed.
7. On refresh failure, mark session expired and prompt `gog auth login`.

Do not store `access_token` or `refresh_token` in manifest, cache, or config
files. Do not log them. Do not pass them as command-line arguments.

### Refresh / Library Discovery (TASK-0005)

1. Call `GET /account/getFilteredProducts?mediaType=1&page=1` to get the
   paginated library.
2. Iterate pages until `page == totalPages`.
3. For each product, store `id`, `title`, `slug`, `worksOn` in the library cache.
4. For download metadata, call `GET https://api.gog.com/products/{id}?expand=downloads`
   per game (or in batches of up to 50 via the batch endpoint).
5. Cache the download metadata separately per product ID.
6. Do not cache `downlink` URLs or signed CDN URLs.

### Download URL (TASK-0007)

1. Look up `files[].downlink` from the cached download metadata.
2. Immediately before starting a download, `GET <downlink>` with a fresh
   Bearer token to resolve the signed CDN URL.
3. Stream the file from the CDN URL, using `Range` headers for resume support.
4. After download, fetch the `checksum` XML and verify MD5 and total size.
5. Never store the signed CDN URL in the manifest.
