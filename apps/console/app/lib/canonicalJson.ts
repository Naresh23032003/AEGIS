// Mirrors aegis.chain.canonical_json (apps/core/aegis/chain.py): sorted
// keys, no whitespace, UTF-8, non-ASCII left as literal characters (not
// \uXXXX escaped). Used for the exact bytes the browser signs in the
// approve/reject/veto flow (plan/04-security.md, plan/02-contracts.md:
// "Signed payload ... is the canonical JSON string of
// {action_id, decision, ts}").

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

function sortKeysDeep(value: Json): Json {
  if (Array.isArray(value)) {
    return value.map(sortKeysDeep);
  }
  if (value !== null && typeof value === "object") {
    const sorted: { [key: string]: Json } = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = sortKeysDeep(value[key] as Json);
    }
    return sorted;
  }
  return value;
}

export function canonicalJson(obj: { [key: string]: Json }): string {
  // JSON.stringify already emits no whitespace with no indent argument and
  // does not escape non-ASCII characters, matching
  // json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False).
  return JSON.stringify(sortKeysDeep(obj));
}
