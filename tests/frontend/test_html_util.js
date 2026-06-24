'use strict';

// Egységteszt a python-processor/static/ui/html.js escapeHtml függvényéhez.
// ESM modul, Node 24 require()-zel betöltve (a meglévő fixture-stílusban).

const { escapeHtml } = require('../../python-processor/static/ui/html.js');

let passed = 0;
function eq(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message} (várt: ${JSON.stringify(expected)}, kapott: ${JSON.stringify(actual)})`);
  passed += 1;
}

eq(escapeHtml('<script>'), '&lt;script&gt;', 'kacsacsőr escape');
eq(escapeHtml('a & b'), 'a &amp; b', 'ampersand escape');
eq(escapeHtml('say "hi"'), 'say &quot;hi&quot;', 'idézőjel escape');
eq(escapeHtml("it's"), 'it&#39;s', 'aposztróf escape');
eq(escapeHtml('<a href="x" o=\'y\'>&</a>'), '&lt;a href=&quot;x&quot; o=&#39;y&#39;&gt;&amp;&lt;/a&gt;', 'vegyes escape');
eq(escapeHtml(null), '', 'null -> üres string');
eq(escapeHtml(undefined), '', 'undefined -> üres string');
eq(escapeHtml(0), '0', 'szám -> string, nincs escapelendő');
eq(escapeHtml('plain text'), 'plain text', 'sima szöveg változatlan');

console.log(`html escape util: PASS (${passed} assertions)`);
