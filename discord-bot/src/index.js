import { Client, GatewayIntentBits, Events } from 'discord.js';
import { loadConfig } from './config.js';
import { createAppContext } from './context.js';
import { commands } from './commands/index.js';
import { dispatchInteraction } from './router.js';

const config = loadConfig();
const appContext = createAppContext(config);

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once(Events.ClientReady, (c) => {
  console.log(`Bot ready as ${c.user.tag}`);
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  try {
    await dispatchInteraction(interaction, { commands, appContext });
  } catch (err) {
    console.error('Unhandled interaction error:', err);
  }
});

client.login(config.discordToken).catch((err) => {
  console.error('Discord login failed:', err.message);
  process.exit(1);
});
