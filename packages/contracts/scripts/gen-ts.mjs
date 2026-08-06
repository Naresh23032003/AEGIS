// Regenerate TypeScript types from packages/contracts/schemas into
// packages/contracts/generated/ts/index.ts. Never hand-edit that file.
import { compileFromFile } from "json-schema-to-typescript";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const schemasDir = join(here, "..", "schemas");
const outDir = join(here, "..", "generated", "ts");
const outFile = join(outDir, "index.ts");

// Entry points only. Each pulls in every schema it $refs (Incident, Evidence,
// ActionProposal, VerifyResult all hang off IncidentState), so compiling the
// closure roots is enough to cover the whole contract surface without
// generating duplicate interfaces.
const entryPoints = ["event-envelope.schema.json", "incident-state.schema.json"];

const banner = `/* eslint-disable */
/**
 * This file was generated from packages/contracts/schemas by json-schema-to-typescript.
 * Do not edit by hand. Regenerate with \`make contracts\`.
 */
`;

async function main() {
  await mkdir(outDir, { recursive: true });
  const parts = [banner];
  for (const entry of entryPoints) {
    const ts = await compileFromFile(join(schemasDir, entry), {
      cwd: schemasDir,
      bannerComment: "",
      style: { semi: true },
    });
    parts.push(ts);
  }
  await writeFile(outFile, parts.join("\n"), "utf8");
  console.log(`wrote ${outFile}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
