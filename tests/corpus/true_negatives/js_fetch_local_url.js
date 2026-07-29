// `fetch(url)` where `url` is a local variable built from a compile-time host.
//
// This was an assertion in tests/test_rules.py that AG006 *should* fire here. It was
// wrong: a variable named `url` says nothing about where its value came from, and every
// AG006 finding in the field measurement was this shape. Converted from a test
// expectation into a corpus true negative so the rule is measured on it rather than
// merely asserted about.
const BASE = "https://api.example.invalid/v1";

export async function loadDocuments(datastoreId) {
  const url = `${BASE}/datastores/${datastoreId}/documents`;
  return fetch(url, { signal: AbortSignal.timeout(30000) });
}
