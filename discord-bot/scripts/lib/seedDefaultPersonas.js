/**
 * Seed the scratch team-tracking DB with three default personas so the
 * playground has usable identities even when the main dev DB is empty.
 *
 * Personas:
 *   - Dev Superuser (discord_id 100000000000000000)
 *   - Dev Admin     (discord_id 100000000000000001)
 *   - Dev Member    (discord_id 100000000000000002)
 *
 * Idempotent — if a person with the same primary_email or a Discord
 * identifier with the same external_id already exists (e.g., because the
 * main DB was copied over first and already contains one), the conflict
 * is caught and ignored.
 *
 * The Discord IDs use the 10^17 range so they never collide with real
 * Discord snowflakes (which are 63-bit and typically start with 8×10^17).
 */

export const DEFAULT_PERSONAS = [
  {
    display_name: 'Dev Superuser',
    primary_email: 'dev-superuser@example.com',
    access_level: 'superuser',
    discord_id: '100000000000000000',
    discord_handle: 'dev-superuser',
  },
  {
    display_name: 'Dev Admin',
    primary_email: 'dev-admin@example.com',
    access_level: 'admin',
    discord_id: '100000000000000001',
    discord_handle: 'dev-admin',
  },
  {
    display_name: 'Dev Member',
    primary_email: 'dev-member@example.com',
    access_level: 'member',
    discord_id: '100000000000000002',
    discord_handle: 'dev-member',
  },
];

async function upsertPerson({ baseUrl, apiKey, persona }) {
  const created = await fetch(`${baseUrl}/people`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'content-type': 'application/json' },
    body: JSON.stringify({
      display_name: persona.display_name,
      primary_email: persona.primary_email,
      access_level: persona.access_level,
    }),
  });
  if (created.status === 201) {
    return (await created.json()).id;
  }
  // Fall back to lookup: person already exists in the copied DB.
  const found = await fetch(
    `${baseUrl}/people/by-email/${encodeURIComponent(persona.primary_email)}`,
    { headers: { 'X-API-Key': apiKey } },
  );
  if (found.ok) return (await found.json()).id;
  return null;
}

async function ensureDiscordIdentifier({ baseUrl, apiKey, personId, persona }) {
  const created = await fetch(`${baseUrl}/people/${personId}/identifiers`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'content-type': 'application/json' },
    body: JSON.stringify({
      provider: 'discord',
      external_id: persona.discord_id,
      handle: persona.discord_handle,
    }),
  });
  // 201 (created) or 409/4xx (already exists / conflict) both count as OK.
  return created.status < 500;
}

export async function seedDefaultPersonas({ baseUrl, apiKey }) {
  for (const persona of DEFAULT_PERSONAS) {
    try {
      const personId = await upsertPerson({ baseUrl, apiKey, persona });
      if (!personId) {
        console.warn(`  seed: could not resolve ${persona.primary_email}`);
        continue;
      }
      await ensureDiscordIdentifier({ baseUrl, apiKey, personId, persona });
      console.log(
        `  ✓ ${persona.access_level.padEnd(9)} ${persona.display_name} (discord=${persona.discord_id})`,
      );
    } catch (e) {
      console.warn(`  seed: ${persona.primary_email} failed: ${e.message}`);
    }
  }
}
