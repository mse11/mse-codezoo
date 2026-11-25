// A level's goal in words, in the current language: "Help the monkey collect every banana".
// Used by the game page and by the teacher's screen (what a shared program was solving).

import { t } from "./i18n.js";

export function describeGoal(level, goal) {
  const pack = level.pack;
  const animal = pack.animalName || pack.animal;
  const one = (tile) => pack.itemNames?.[tile]?.one || pack.items[tile] || "item";
  const many = (tile) => pack.itemNames?.[tile]?.many || one(tile);
  switch (goal.type) {
    case "free":
      return t("No goal: make the {animal} do anything you like and tell a story", { animal });
    case "collect_all": {
      let text = t("Help the {animal} collect every {item}", { animal, item: one(goal.item), items: many(goal.item) });
      if (goal.avoid) text += `, ${t("but leave every {item} alone", { item: one(goal.avoid) })}`;
      return text;
    }
    case "reach":
      return t("Help the {animal} reach square ({x}, {y})", { animal, x: goal.at[0], y: goal.at[1] });
    case "say":
      if (goal.texts) return t("Make the {animal} say: {texts}", { animal, texts: goal.texts.map((x) => `“${x}”`).join(", ") });
      return t("Make the {animal} say “{text}”", { animal, text: goal.text });
    case "avoid":
      return t("Leave every {item} alone", { item: one(goal.item) });
    case "print":
      if (goal.lines) return t("Make the program print: {texts}", { texts: goal.lines.map((x) => `“${x}”`).join(", ") });
      return t("Make the program print “{text}”", { text: goal.text });
    case "time":
      return t("Be done by tick {n} of the clock", { n: goal.within });
    case "file":
      return t("Leave the right text in the file {name}", { name: goal.name });
    case "build":
      return t("Build a dam from exactly: {logs}", {
        logs: Object.entries(goal.logs).map(([log, n]) => `${n} × ${log}`).join(", "),
      });
    case "all":
      return goal.goals
        .map((part, i) => {
          const text = describeGoal(level, part);
          return i ? text.charAt(0).toLowerCase() + text.slice(1) : text;
        })
        .join("; ");
  }
  return goal.type;
}
