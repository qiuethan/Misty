const REQUIRED = [
  'DISCORD_TOKEN',
  'DISCORD_CLIENT_ID',
  'DISCORD_GUILD_ID',
  'DIRECTORY_BASE_URL',
  'DIRECTORY_API_KEY',
];

export function loadConfig(env = process.env) {
  const missing = REQUIRED.filter((k) => !env[k]);
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(', ')}`);
  }
  return {
    discordToken: env.DISCORD_TOKEN,
    discordClientId: env.DISCORD_CLIENT_ID,
    discordGuildId: env.DISCORD_GUILD_ID,
    directoryBaseUrl: env.DIRECTORY_BASE_URL.replace(/\/+$/, ''),
    directoryApiKey: env.DIRECTORY_API_KEY,
  };
}
