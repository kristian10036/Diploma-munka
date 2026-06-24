// html.js
// -----------------------------------------------------------------------------
// Általános, megosztott HTML-szöveg escapelő segédfüggvény. Az index.html inline
// scriptjéből emelve, viselkedésmegőrző módon (a függvénytest szó szerint
// változatlan). Tiszta: csak az argumentumából dolgozik, nincs DOM- vagy
// modul-szintű state-függősége. Több view-modul (spektrum-popover, eszköz-
// megfigyelési táblázatok, retention) közös függősége.
// -----------------------------------------------------------------------------

export function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
