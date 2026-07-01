// Authorization: evaluate a command's declarative auth policy against a Principal.
//
// v1 vocabulary:
//   'public' -> no identity required
//   'linked' -> caller must be authenticated (a non-null Principal)
//
// Extension point: a future policy could be an object, e.g. { minRole:
// 'executive' } or { teamAdmin: true }, evaluated against principal.person's
// directory roles. Add a branch here; the authorize() signature and the router
// stay the same. Unknown policies deny (fail closed).
export function authorize(policy, principal) {
  if (policy === 'public') return { ok: true };
  if (policy === 'linked') {
    return principal ? { ok: true } : { ok: false, reason: 'not_linked' };
  }
  return { ok: false, reason: 'unknown_policy' };
}
