// canvas-util.js
// -----------------------------------------------------------------------------
// Tiszta canvas-/geometria-segédfüggvények a spektrum-rajzoláshoz: plot-on-belüli
// hit-teszt, lekerekített téglalap útvonal (a megadott 2D contextre dolgozik) és
// a dBm -> RGB szín-leképezés a vízeséshez. Az index.html inline scriptjéből
// emelve, a függvénytestek szó szerint változatlanok. A clamp-et a
// spectrum-scale.js-ből importálja; app-szintű state-et nem olvas.
// -----------------------------------------------------------------------------

import { clamp } from './spectrum-scale.js';

export function inPlot(x,y,plot){ return x >= plot.left && x <= plot.left + plot.width && y >= plot.top && y <= plot.top + plot.height; }

export function roundRect(ctx,x,y,w,h,r,fill,stroke){
  ctx.beginPath();
  ctx.moveTo(x+r,y);
  ctx.arcTo(x+w,y,x+w,y+h,r);
  ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r);
  ctx.arcTo(x,y,x+w,y,r);
  ctx.closePath();
  if(fill) ctx.fill();
  if(stroke) ctx.stroke();
}

export function dbmToColor(dbm){
  if (!Number.isFinite(dbm)) return [0,0,0,0];
  let t = (dbm - (-100)) / 72;
  t = clamp(t,0,1);
  let r,g,b;
  if (t < .20) { r=0; g=0; b=Math.round(70 + t/.20*185); }
  else if (t < .40) { r=0; g=Math.round((t-.20)/.20*255); b=255; }
  else if (t < .62) { r=0; g=255; b=Math.round(255 - (t-.40)/.22*255); }
  else if (t < .82) { r=Math.round((t-.62)/.20*255); g=255; b=0; }
  else { r=255; g=Math.round(255 - (t-.82)/.18*205); b=0; }
  return [r,g,b];
}
