import * as link from './link.js';
import * as whoami from './whoami.js';

// Single source of truth for the command set: consumed by the router (dispatch)
// and by registerCommands.js (Discord registration). Add a command = one import
// + one entry here.
export const commands = new Map([
  [link.data.name, link],
  [whoami.data.name, whoami],
]);
