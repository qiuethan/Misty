import * as link from './link.js';
import * as whoami from './whoami.js';
import * as seed from './seed.js';
import * as team from './team.js';
import * as myTeams from './my-teams.js';

// Single source of truth for the command set: consumed by the router (dispatch)
// and by registerCommands.js (Discord registration). Add a command = one import
// + one entry here.
export const commands = new Map([
  [link.data.name, link],
  [whoami.data.name, whoami],
  [seed.data.name, seed],
  [team.data.name, team],
  [myTeams.data.name, myTeams],
]);

// Split a command list into release channels for registration:
// - stable commands register globally (every production server)
// - beta commands (`export const beta = true`) register ONLY to the dedicated
//   testing guild, so they stay exclusive to that server and never reach prod.
export function partitionCommands(list) {
  return {
    stable: list.filter((c) => !c.beta),
    beta: list.filter((c) => c.beta),
  };
}
