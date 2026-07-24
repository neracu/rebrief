Another source of false positives in the secret detector: constants like `const STORAGE_KEY = “vast:last-project:v2”` and `const STORAGE_KEY = “vast:pinned-projects:v1”` are namespaced identifiers for localStorage/sessionStorage, not secrets. They pass the current check, apparently because the variable name (STORAGE_KEY) contains “KEY” and the value is long enough.

Add an additional filter to the “looks like a secret” check: a value is NOT considered a secret if it:
- contains a “:” character as a separator (a typical pattern for namespaced storage keys: “app:feature:version”),
- consists entirely of lowercase letters, digits, hyphens, and colons (no mixed uppercase letters, no mixed-case or Base64 characters),
- reads as a natural, human-composed identifier rather than a random string.

Also consider a more general rule: if a value entirely matches the pattern `^[a-z0-9]+(:[a-z0-9-]+)+$` (namespace:feature:version), exclude it from secret detection regardless of the variable name.

Add unit tests 

Run the tests on fixtures with real secrets—they should still be detected. 