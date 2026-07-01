import { REST, Routes } from 'discord.js';
import { loadConfig } from './config.js';
import { commands, partitionCommands } from './commands/index.js';

const config = loadConfig();
const { stable, beta } = partitionCommands([...commands.values()]);
const stableBody = stable.map((c) => c.data.toJSON());
const betaBody = beta.map((c) => c.data.toJSON());

const rest = new REST({ version: '10' }).setToken(config.discordToken);

// Stable commands register GLOBALLY — available in every server (production).
// Global commands can take up to ~1 hour to propagate.
await rest.put(Routes.applicationCommands(config.discordClientId), { body: stableBody });
console.log(`Registered ${stableBody.length} stable commands globally (all servers).`);

// Beta commands register ONLY to the dedicated testing guild, so they stay
// exclusive to that server and never reach production.
if (config.discordGuildId) {
  // Registering betaBody (which may be empty) also CLEARS any previously
  // registered guild commands, so promoted/removed beta commands don't linger.
  await rest.put(
    Routes.applicationGuildCommands(config.discordClientId, config.discordGuildId),
    { body: betaBody },
  );
  console.log(
    `Registered ${betaBody.length} beta commands to testing guild ${config.discordGuildId} (exclusive).`,
  );
} else if (betaBody.length > 0) {
  console.warn(
    `${betaBody.length} beta command(s) NOT registered: set DISCORD_GUILD_ID to a testing guild to register them.`,
  );
}
