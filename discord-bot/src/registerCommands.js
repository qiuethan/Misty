import { REST, Routes } from 'discord.js';
import { loadConfig } from './config.js';
import { commands } from './commands/index.js';

const config = loadConfig();
const body = [...commands.values()].map((c) => c.data.toJSON());

const rest = new REST({ version: '10' }).setToken(config.discordToken);
await rest.put(
  Routes.applicationGuildCommands(config.discordClientId, config.discordGuildId),
  { body },
);
console.log(`Registered ${body.length} guild commands.`);
