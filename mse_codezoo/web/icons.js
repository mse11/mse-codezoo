// Sound icons, drawn as simple outlines in the text's own colour (like the "3D" button), so
// they read well in light, dark and high-contrast colours. Emoji such as 🎵 🗣️ 🔊 come in
// the device's fixed colours (a dark purple on Windows) and get lost on a dark background.
//
//   icon("note")      sounds on (🎵)        icon("music")       game music (🎶)
//   icon("speaker")   read it aloud (🔊)    icon("speaker-off") quiet (🔇)
//   icon("guide")     the guide's voice (🗣️), a head speaking
//
// The shapes are drawn here (no icon font or files), on a 24 x 24 grid.

const SHAPES = {
  note: `<path d="M9 17.5V5.5l10-2.5v11.5"/><circle cx="6.5" cy="17.5" r="2.5" fill="currentColor"/><circle cx="16.5" cy="14.5" r="2.5" fill="currentColor"/>`,
  music: `<path d="M8 18.5V6l8-2.5V16"/><circle cx="5.5" cy="18.5" r="2.5" fill="currentColor"/><circle cx="13.5" cy="16" r="2.5" fill="currentColor"/><path d="M19 7.5l2.5-1.5M19.5 11h2.5"/>`,
  speaker: `<path d="M3.5 9.5h3.5l4.5-4v13l-4.5-4H3.5z" fill="currentColor"/><path d="M15 9a4 4 0 0 1 0 6M17.5 6.5a7.5 7.5 0 0 1 0 11"/>`,
  "speaker-low": `<path d="M3.5 9.5h3.5l4.5-4v13l-4.5-4H3.5z" fill="currentColor"/><path d="M15 9a4 4 0 0 1 0 6"/>`,
  "speaker-off": `<path d="M3.5 9.5h3.5l4.5-4v13l-4.5-4H3.5z" fill="currentColor"/><path d="M15.5 9.5l5 5M20.5 9.5l-5 5"/>`,
  // a head seen from the side, filled (a thin outline is hard to read this small), and its
  // voice as two waves in front of the mouth
  guide: `<path d="M3.5 21v-2.6a7.2 7.2 0 0 1-1.5-4.6C2 9.5 5.3 6 9.3 6c3.9 0 6.9 3 6.9 6.6l1.6 2.6-1.6.7v2a1.6 1.6 0 0 1-1.6 1.6h-2.4V21z" fill="currentColor"/><path d="M19.2 8.6a3.6 3.6 0 0 1 0 4.8M21.4 6.4a6.8 6.8 0 0 1 0 9.2"/>`,
};

// the icon as an element: <span class="icon"><svg>…</svg></span>, hidden from screen
// readers (the button around it has the words)
export function icon(name) {
  const span = document.createElement("span");
  span.className = `icon icon-${name}`;
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${SHAPES[name] || ""}</svg>`;
  return span;
}

// pages written in HTML mark the places with <span data-icon="note"></span>
export function fillIcons(root = document) {
  for (const place of root.querySelectorAll("[data-icon]")) {
    place.replaceWith(icon(place.dataset.icon));
  }
}
