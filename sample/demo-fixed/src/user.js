export function verifyIdentity(form) {
  const ci = form.get("ci");
  return checkWithAgency(ci);
}
