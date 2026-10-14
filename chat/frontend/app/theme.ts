/** ChatWork's Theme button: a random ramp from the original palette, dark or light. */

/** The `colors` array of the original base.html: 13 ramps of 9 shades, darkest to lightest. */
export const COLORS: readonly (readonly string[])[] = [
  ["#200000", "#660000", "#990000", "#cc0000", "#ff0000", "#ff2020", "#ff6666", "#ff9999", "#ffcccc"],
  ["#201900", "#662000", "#994c00", "#cc6600", "#ff8000", "#ff9920", "#ffb266", "#ffcc99", "#ffe5cc"],
  ["#202000", "#666600", "#999900", "#cccc00", "#ffff00", "#ffff20", "#ffff66", "#ffff99", "#ffffcc"],
  ["#192000", "#206600", "#4c9900", "#66cc00", "#80ff00", "#99ff20", "#b2ff66", "#ccff99", "#e5ffcc"],
  ["#002000", "#006600", "#009900", "#00cc00", "#00ff00", "#20ff20", "#66ff66", "#99ff99", "#ccffcc"],
  ["#002019", "#006620", "#00994c", "#00cc66", "#00ff80", "#20ff99", "#66ffb2", "#99ffcc", "#ccffe5"],
  ["#002020", "#006666", "#009999", "#00cccc", "#00ffff", "#20ffff", "#66ffff", "#99ffff", "#ccffff"],
  ["#001920", "#002066", "#004c99", "#0066cc", "#0080ff", "#2099ff", "#66b2ff", "#99ccff", "#cce5ff"],
  ["#000020", "#000066", "#000099", "#0000cc", "#0000ff", "#2020ff", "#6666ff", "#9999ff", "#ccccff"],
  ["#190020", "#200066", "#4c0099", "#6600cc", "#7f00ff", "#9920ff", "#b266ff", "#cc99ff", "#e5ccff"],
  ["#200020", "#660066", "#990099", "#cc00cc", "#ff00ff", "#ff20ff", "#ff66ff", "#ff99ff", "#ffccff"],
  ["#200019", "#660020", "#99004c", "#cc0066", "#ff007f", "#ff2099", "#ff66b2", "#ff99cc", "#ffcce5"],
  ["#000000", "#202020", "#404040", "#606060", "#808080", "#a0a0a0", "#c0c0c0", "#e0e0e0", "#ffffff"],
];

export interface ThemeColors {
  background: string;
  border: string;
  text: string;
}

/** Original rule: dark = shades 0/7/8, light = shades 8/1/0 (background/border/text). */
export function pickTheme(random: () => number = Math.random): ThemeColors {
  const ramp = COLORS[Math.min(COLORS.length - 1, Math.floor(random() * COLORS.length))];
  return random() < 0.5
    ? { background: ramp[0], border: ramp[7], text: ramp[8] }
    : { background: ramp[8], border: ramp[1], text: ramp[0] };
}

/** Set (or replace) one rule in the page's own <style> sheet, like the original overwriteCSS(). */
export function overwriteCSS(selector: string, style: string, doc: Document = document): void {
  let sheet = [...doc.styleSheets].find((s) => !s.href);
  if (!sheet) {
    const el = doc.createElement("style");
    doc.head.appendChild(el);
    sheet = el.sheet as CSSStyleSheet;
  }
  const rules = Array.from(sheet.cssRules) as CSSStyleRule[];
  const existing = rules.find((rule) => rule.selectorText === selector);
  if (existing) existing.style.cssText = style;
  else sheet.insertRule(`${selector} { ${style} }`, rules.length);
}

export function applyTheme({ background, border, text }: ThemeColors, doc: Document = document): void {
  overwriteCSS("*", `background: ${background}; color: ${text}; border-color: ${border}`, doc);
  overwriteCSS("button:hover", `background-color: ${text}; color: ${background}`, doc);
  overwriteCSS("::selection", `background-color: ${text}; color: ${background}`, doc);
  overwriteCSS(".selected", `background-color: ${text}; color: ${background}`, doc);
  overwriteCSS(".selected *", `background-color: ${text}; color: ${background}`, doc);
}

/** Pick and apply a new random theme. */
export function shuffleTheme(random: () => number = Math.random): ThemeColors {
  const colors = pickTheme(random);
  applyTheme(colors);
  return colors;
}
