import { REST, Routes } from 'discord.js';
import { loadConfig } from './config.js';
import { commands } from './commands/index.js';

const config = loadConfig();
const body = [...commands.values()].map((c) => c.data.toJSON());

const rest = new REST({ version: '10' }).setToken(config.discordToken);

// Always register globally so the bot's commands work in every server it joins
// (production). Global commands can take up to ~1 hour to propagate.
await rest.put(Routes.applicationCommands(config.discordClientId), { body });
console.log(`Registered ${body.length} commands globally (all servers).`);

// If a dedicated testing guild is configured, ALSO register there so command
// changes appear instantly while developing. Note: the testing guild will list
// these commands twice — once from this guild registration and once from the
// global set — which is expected and harmless in a throwaway test server.
if (config.discordGuildId) {
  await rest.put(
    Routes.applicationGuildCommands(config.discordClientId, config.discordGuildId),
    { body },
  );
  console.log(
    `Also registered ${body.length} commands to testing guild ${config.discordGuildId} (instant).`,
  );
}
