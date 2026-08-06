// Approver keypair: generated once per browser with tweetnacl (Ed25519),
// stored in IndexedDB (idb-keyval) so it survives refresh, registered with
// core-api via POST /keys. plan/05-frontend.md, Approval and veto
// overlays: "tweetnacl keygen on first visit, IndexedDB storage, POST
// /keys registration, signing flow." plan/04-security.md: the browser
// signs, the server only ever verifies (apps/core/aegis/security.py has
// no signing function by design); this module is the one place that signs.

import { get, set } from "idb-keyval";
import nacl from "tweetnacl";

import { registerKey } from "./api";
import { canonicalJson } from "./canonicalJson";
import { fromHex, toHex } from "./hex";

const STORE_KEY = "aegis-approver-keypair";

export interface ApproverKeypair {
  publicKeyHex: string;
  secretKeyHex: string;
  label: string;
}

let cached: Promise<ApproverKeypair> | null = null;
let registeredFor: string | null = null;

async function generate(): Promise<ApproverKeypair> {
  const pair = nacl.sign.keyPair();
  const publicKeyHex = toHex(pair.publicKey);
  const keypair: ApproverKeypair = {
    publicKeyHex,
    secretKeyHex: toHex(pair.secretKey),
    label: `console-${publicKeyHex.slice(0, 8)}`,
  };
  await set(STORE_KEY, keypair);
  return keypair;
}

export function getOrCreateKeypair(): Promise<ApproverKeypair> {
  if (!cached) {
    cached = (async () => {
      const existing = await get<ApproverKeypair>(STORE_KEY);
      return existing ?? (await generate());
    })();
  }
  return cached;
}

/** Registers the keypair with core-api if this session hasn't yet; safe to
 * call before every signed action since POST /keys is an upsert. */
export async function ensureRegistered(): Promise<ApproverKeypair> {
  const kp = await getOrCreateKeypair();
  if (registeredFor !== kp.publicKeyHex) {
    await registerKey(kp.publicKeyHex, kp.label);
    registeredFor = kp.publicKeyHex;
  }
  return kp;
}

export interface SignedDecision {
  decision: "approve" | "reject" | "veto";
  pubkey: string;
  signed_payload: string;
  signature: string;
}

/** Signs canonical_json({action_id, decision, ts}) with the local secret
 * key, matching aegis.security.signed_payload byte for byte. */
export async function signDecision(
  actionId: string,
  decision: "approve" | "reject" | "veto",
): Promise<SignedDecision> {
  const kp = await ensureRegistered();
  const ts = new Date().toISOString();
  const signedPayload = canonicalJson({ action_id: actionId, decision, ts });
  const signature = nacl.sign.detached(
    new TextEncoder().encode(signedPayload),
    fromHex(kp.secretKeyHex),
  );
  return {
    decision,
    pubkey: kp.publicKeyHex,
    signed_payload: signedPayload,
    signature: toHex(signature),
  };
}
