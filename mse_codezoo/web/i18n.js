// Interface language (English, Slovak). Keys are the English text, as in the engine's
// mse_codezoo/i18n.py; the engine translates its own messages, titles and hints.
// Python keywords and command names (for, step, grab) are never translated.

const LANG_KEY = "codezoo.lang";
export const LANGS = { en: "English", sk: "Slovenčina" };

const SK = {
  // header and panes
  "▶ Run": "▶ Spusti",
  "⏸ Pause": "⏸ Pauza",
  "Step": "Krok",
  "Reset": "Znova",
  "Speed": "Rýchlosť",
  "Who's playing?": "Kto sa hrá?",
  "Grown-ups": "Dospelí",
  "Stage": "Scéna",
  "Blocks": "Bloky",
  "Code": "Kód",
  "let me type": "chcem písať",
  "Choose a level": "Vyber level",
  "Language": "Jazyk",
  "3D": "3D",
  "2D": "2D",
  "Show the stage in 3D": "Zobraziť scénu v 3D",
  "Resize the stage": "Zmeniť veľkosť scény",
  "Resize blocks and code": "Zmeniť pomer blokov a kódu",
  "Python code": "Kód v Pythone",
  "Hint": "Rada",
  "World": "Svet",
  "Your program must work in every world. Try them all!": "Program musí fungovať v každom svete. Vyskúšaj všetky!",
  "This program has a bug. Run it, watch, then fix it!": "V tomto programe je chyba. Spusti ho, sleduj a oprav ho!",
  "Stars for: {rules}": "Hviezdičky za: {rules}",
  "just solving it": "vyriešenie",
  "{n} lines or fewer": "najviac {n} riadkov",
  "use {what}": "použi {what}",
  "Help the {animal} collect every {item}": "Pomôž: zozbieraj všetky {items}",
  "but leave every {item} alone": "ale nechaj tak každý {item}",
  "Help the {animal} reach square ({x}, {y})": "Pomôž dostať sa na políčko ({x}, {y})",
  "Make the {animal} say “{text}”": "Nech zaznie „{text}“",
  "Make the {animal} say: {texts}": "Nech zaznie: {texts}",
  "Leave every {item} alone": "Nechaj tak každý {item}",
  "Python can't read this program yet. Look under the code.": "Python tomuto programu zatiaľ nerozumie. Pozri sa pod kód.",
  "Line {line}: ": "Riadok {line}: ",
  "line {line}: {message}": "riadok {line}: {message}",
  "{n} of 3 stars": "{n} z 3 hviezdičiek",
  "Could not start: {message}": "Nepodarilo sa spustiť: {message}",
  "Guest": "Hosť",
  // blocks
  "step %1": "krok %1",
  "turn left ↺": "otoč sa doľava ↺",
  "turn right ↻": "otoč sa doprava ↻",
  "grab": "chyť",
  "say %1": "povedz %1",
  "print %1": "vypíš %1",
  "repeat %1 times (count with %2)": "opakuj %1-krát (počítaj s %2)",
  "repeat while %1": "opakuj, kým %1",
  "if %1": "ak %1",
  "else": "inak",
  "set %1 to %2": "nastav %1 na %2",
  "change %1 %2 %3": "zmeň %1 %2 %3",
  "not %1": "nie je %1",
  "and": "a zároveň",
  "or": "alebo",
  "is blocked?": "je cesta zatarasená?",
  "item here": "čo je tu",
  "item ahead": "čo je vpredu",
  "text of %1": "text z %1",
  "Walk forward this many squares.": "Choď dopredu o toľkoto políčok.",
  "Turn a quarter to the left.": "Otoč sa o štvrť kruhu doľava.",
  "Turn a quarter to the right.": "Otoč sa o štvrť kruhu doprava.",
  "Pick up what is on this square.": "Zdvihni, čo leží na tomto políčku.",
  "Show a speech bubble.": "Ukáž bublinu s textom.",
  "Write a line under the stage.": "Vypíš riadok pod scénu.",
  "Do the blocks inside again and again.": "Opakuj bloky vnútri znova a znova.",
  "Repeat the blocks inside as long as the question is true.": "Opakuj bloky vnútri, kým platí otázka.",
  "Do the blocks inside only when the question is true.": "Urob bloky vnútri, len keď platí otázka.",
  "One way when the question is true, the other way when it is not.": "Jedna cesta, keď otázka platí, druhá, keď nie.",
  "Put a value in a box with a name (a variable).": "Vlož hodnotu do škatuľky s menom (premennej).",
  "Change the value in a variable.": "Zmeň hodnotu v premennej.",
  "A number.": "Číslo.",
  "Text, between quotes.": "Text v úvodzovkách.",
  "Yes or no.": "Áno alebo nie.",
  "The value inside a variable.": "Hodnota v premennej.",
  "Count with two values.": "Počítaj s dvoma hodnotami.",
  "Compare two values: the answer is True or False.": "Porovnaj dve hodnoty: odpoveď je True alebo False.",
  "Both must be true (and), or one is enough (or).": "Musia platiť obe (and), alebo stačí jedna (or).",
  "The opposite: True becomes False.": "Opak: z True je False.",
  "Ask the world a question.": "Opýtaj sa sveta na otázku.",
  "Turn a value into text.": "Urob z hodnoty text.",
  "A text command: big letters, small letters...": "Príkaz textu: veľké písmená, malé písmená...",
  "A note for people. The animal ignores it.": "Poznámka pre ľudí. Zvieratko ju ignoruje.",
  "Code that has no block yet. It is kept exactly as typed.": "Kód, ktorý ešte nemá blok. Zostane presne tak, ako bol napísaný.",
  "a note": "poznámka",
  // players and grown-ups
  "Just try it": "Len skúsim",
  "nothing is saved": "nič sa neukladá",
  "New player": "Nový hráč",
  "Name": "Meno",
  "Picture": "Obrázok",
  "Start playing": "Začni hrať",
  "This part is for parents and teachers.": "Táto časť je pre rodičov a učiteľov.",
  "What is {a} times {b}?": "Koľko je {a} krát {b}?",
  "Open": "Otvoriť",
  "Back to the zoo": "Späť do zoo",
  "Not quite. This part is for grown-ups.": "Nie celkom. Táto časť je pre dospelých.",
  "Settings": "Nastavenia",
  "Daily play limit per player": "Denný limit hrania pre hráča",
  "no limit": "bez limitu",
  "{n} minutes": "{n} minút",
  "1 hour": "1 hodina",
  "1.5 hours": "1,5 hodiny",
  "Private mode: keep only stars and solved levels": "Súkromný režim: ukladať len hviezdičky a vyriešené levely",
  "New PIN (4–8 digits, optional)": "Nový PIN (4–8 číslic, nepovinné)",
  "Remove the PIN": "Odstrániť PIN",
  "Save settings": "Uložiť nastavenia",
  "Saved.": "Uložené.",
  "Players": "Hráči",
  "No players yet.": "Zatiaľ žiadni hráči.",
  "Idea": "Nápad",
  "Status": "Stav",
  "Progress": "Pokrok",
  "{solved} of {levels} levels": "{solved} z {levels} levelov",
  "{levels} solved · {stars} · {minutes} in the last 7 days": "vyriešené: {levels} · {stars} · {minutes} za posledných 7 dní",
  "Often: {list}.": "Často: {list}.",
  "Try at home: {tip}": "Skúste doma: {tip}",
  "Save progress to a file": "Uložiť pokrok do súboru",
  "Remove player": "Odstrániť hráča",
  "Remove {name} and all their progress? This can't be undone.": "Odstrániť hráča {name} a celý jeho pokrok? Nedá sa to vrátiť späť.",
  "That's all for today!": "To je na dnes všetko!",
  "The {animal} is tired and going to sleep. Great work today — see you tomorrow!": "Zvieratko je unavené a ide spať. Dnes si pracoval skvele, uvidíme sa zajtra!",
  "Another player": "Iný hráč",
  "level": "level",
  "levels": "levelov",
  "star": "hviezdička",
  "stars": "hviezdičiek",
  "minute": "minúta",
  "minutes": "minút",
  // report statuses and concepts
  "mastered": "zvládnuté",
  "practised": "precvičené",
  "met": "videné",
  "not yet": "zatiaľ nie",
  // try-at-home tips
  "Play “robot” on the floor: one of you gives step and turn commands, the other walks them.": "Zahrajte sa na robota: jeden dáva príkazy krok a otoč sa, druhý ich chodí.",
  "Spell a command together before typing it, then check it letter by letter.": "Pred písaním príkaz spolu vyhláskujte a potom ho skontrolujte písmeno po písmene.",
  "Look for pairs together: every ( needs a ).": "Hľadajte spolu dvojice: každá ( potrebuje ).",
  "Before pressing Run, ask: where will the animal stop?": "Pred spustením sa opýtajte: kde zvieratko zastane?",
  "Ask: can we do the same with fewer blocks?": "Opýtajte sa: dá sa to isté urobiť s menej blokmi?",
  "Ask: which blocks repeat? Could a loop do that for us?": "Opýtajte sa: ktoré bloky sa opakujú? Nemohol by to urobiť cyklus?",
  "Play “Simon says, but only if”: act only when a rule is true, like “jump if I hold up a banana”.": "Hrajte sa „Simon hovorí, ale len ak“: konajte len keď platí pravidlo, napríklad „skoč, ak zdvihnem banán“.",
  "Sort objects at home into boxes and label them: is this a number, a word, or yes/no?": "Triedte doma veci do krabíc a označte ich: je to číslo, slovo, alebo áno/nie?",
  // phase 3
  "Only the {animal} can play this level.": "Tento level hrá len toto zviera: {animal}.",
  "Helper file {name}.py (import it)": "Pomocný súbor {name}.py (importuj ho)",
  "Build a dam from exactly: {logs}": "Postav hrádzu presne z: {logs}",
  "a function that calls itself": "funkcia, ktorá volá samu seba",
  "Where it happened, from the outside in:": "Kde sa to stalo, zvonku dnu:",
  "… {n} more …": "… ďalších {n} …",
  "line {line}, in the program": "riadok {line}, v programe",
  "line {line}, in {function}()": "riadok {line}, vo {function}()",
  "New sticker: {name}": "Nová nálepka: {name}",
  "Practise first": "Najprv si precvič",
  "Tricky one! Want to practise {concept} on “{title}” first? You can come back any time.": "Ťažký level! Chceš si najprv precvičiť {concept} na leveli „{title}“? Vrátiť sa môžeš kedykoľvek.",
  "📖 Make a storybook": "📖 Urob knižku",
  "💾 Save this run": "💾 Ulož tento beh",
  "Every sticker is in the habitat.": "Všetky nálepky sú už v domčeku.",
  "Solve levels to earn stickers!": "Rieš levely a získaj nálepky!",
  "Needs {n} stickers": "Treba nálepiek: {n}",
  "nothing": "nič",
  "Play it now": "Zahraj si ho teraz",
  "You already have this card's sticker.": "Nálepku z tejto karty už máš.",
  "The camera is not available. Type the code instead.": "Kamera nie je dostupná. Napíš radšej kód.",
  "Choose an animal": "Vyber zviera",
  "My zoo": "Moja zoo",
  "Level editor": "Editor levelov",
  "Call stack": "Zásobník volaní",
  "Drag your stickers around the habitat. Tap a sticker below to put it in.": "Ťahaj nálepky po domčeku. Ťukni na nálepku dole a vložíš ju dnu.",
  "Habitat": "Domček",
  "Dress up": "Oblečenie",
  "Played a card away from the screen?": "Zahral si si kartu bez obrazovky?",
  "Card code": "Kód karty",
  "Unlock": "Odomkni",
  "Scan the card": "Naskenuj kartu",
  "Print cards": "Vytlačiť karty",
  "stop the loop": "zastav cyklus",
  "Leave the loop right now.": "Hneď opusti cyklus.",
  "skip to the next turn": "preskoč na ďalšie kolo",
  "Jump to the next turn of the loop.": "Skoč na ďalšie kolo cyklu.",
  "teach %1 with inputs %2": "nauč %1 so vstupmi %2",
  "Teach a new command. Its inputs are names, split by commas.": "Nauč nový príkaz. Jeho vstupy sú mená oddelené čiarkami.",
  "do %1 %2 %3": "urob %1 %2 %3",
  "Use a command you taught with `def`.": "Použi príkaz, ktorý si naučil cez `def`.",
  "answer of %1 %2 %3": "odpoveď z %1 %2 %3",
  "What a command you taught gives back.": "Čo vráti príkaz, ktorý si naučil.",
  "give back %1": "vráť %1",
  "End the command and give back a value.": "Ukonči príkaz a vráť hodnotu.",
  "try": "skús",
  "if %1 happens (call it %2)": "ak nastane %1 (nazvi ju %2)",
  "Try something; if that error happens, do the other blocks instead.": "Skús niečo; ak nastane tá chyba, urob radšej ostatné bloky.",
  "raise %1 %2": "vyhoď %1 %2",
  "Stop with an error of your own.": "Zastav vlastnou chybou.",
  "for each %1 in %2": "pre každé %1 v %2",
  "Do the blocks inside once for every item.": "Urob bloky vnútri raz pre každú položku.",
  "add %1 to the list %2": "pridaj %1 do zoznamu %2",
  "Put one more item at the end of a list.": "Pridaj ešte jednu položku na koniec zoznamu.",
  "from %1 bring %2": "z %1 prines %2",
  "Bring commands from a helper file.": "Prines príkazy z pomocného súboru.",
  "change the outside %1": "meň vonkajšie %1",
  "Let this command change a variable from outside it.": "Dovoľ tomuto príkazu meniť premennú zvonku.",
  "The animal's own trick.": "Vlastný trik zvieraťa.",
  "build %1": "postav %1",
  "Lay a log into the water ahead.": "Polož poleno do vody pred sebou.",
  "A list of things. Empty sockets are left out.": "Zoznam vecí. Prázdne miesta sa vynechajú.",
  "how many in %1": "koľko je v %1",
  "How many items, or letters in a text.": "Koľko je položiek alebo písmen v texte.",
  "One item: by its position in a list, or by its key in a dictionary.": "Jedna položka: podľa poradia v zozname alebo podľa kľúča v slovníku.",
  "%1 get %2 or %3": "%1 daj %2 alebo %3",
  "The value for a key, or the other value when the key is missing.": "Hodnota pre kľúč, alebo tá druhá, keď kľúč chýba.",
  "pairs in %1": "dvojice v %1",
  "Every key with its value.": "Každý kľúč s jeho hodnotou.",
  "Prototype: paint a world, write a solution, test it, download the files.": "Prototyp: nakresli svet, napíš riešenie, otestuj ho, stiahni súbory.",
  "Width": "Šírka",
  "Height": "Výška",
  "Animal": "Zviera",
  "Tile": "Políčko",
  "Start facing": "Na začiatku otočené",
  "Pick “start”, then tap the square where the animal begins.": "Vyber „štart“ a ťukni na políčko, kde zviera začína.",
  "Level id": "Id levelu",
  "Title": "Názov",
  "Module": "Modul",
  "Goal": "Cieľ",
  "collect every item": "zozbierať všetky veci",
  "reach the flag": "dôjsť k vlajke",
  "say a text": "povedať text",
  "Item": "Vec",
  "Text": "Text",
  "Must use (node types, split by commas)": "Musí použiť (typy uzlov oddelené čiarkami)",
  "Hints, one per line": "Rady, jedna na riadok",
  "Starter program (optional, for a bug to fix)": "Úvodný program (nepovinný, s chybou na opravu)",
  "Reference solution": "Vzorové riešenie",
  "Test the level": "Otestuj level",
  "Download the files": "Stiahni súbory",
  "Open a level file": "Otvor súbor levelu",
  "Level JSON": "JSON levelu",
  "ground": "zem",
  "rock": "skala",
  "water": "voda",
  "tree": "strom",
  "thin ice": "tenký ľad",
  "watched": "strážené",
  "start": "štart",
  "flag": "vlajka",
  "Testing…": "Testujem…",
  "The solution earns every star, in every world and for every animal that can play it.": "Riešenie získa všetky hviezdičky, v každom svete a pre každé zviera, ktoré level hrá.",
  "Not yet:": "Ešte nie:",
  "That file is not a level: {message}": "Tento súbor nie je level: {message}",
  "Russian dolls: open one, then the next, until the smallest. That is a base case!": "Matriošky: otvor jednu, potom ďalšiu, až po najmenšiu. To je základný prípad!",
  "Plan a “what if it goes wrong?” together: if it rains, we take an umbrella.": "Vymyslite spolu „čo ak sa to pokazí?“: ak prší, vezmeme si dáždnik.",
};

const CONCEPTS = {
  en: {
    call: "commands", order: "order", comment: "comments", for: "for loops", range: "range",
    variable: "variables", update: "changing variables", text: "text", type: "types",
    fstring: "f-strings", method: "text commands", index: "picking letters", if: "if",
    else: "else", elif: "elif", compare: "comparing", and_or: "and / or", not: "not",
    sensor: "asking the world", debugging: "finding bugs", while: "while loops",
    break: "break", continue: "continue", "nested loops": "loops in loops", variables: "variables",
    def: "functions", parameters: "inputs", defaults: "default values", return: "return",
    import: "helper files", global: "global", try: "try", except: "except", ValueError: "ValueError",
    raise: "raise", assert: "assert", lists: "lists", types: "types", tuples: "tuples",
    unpacking: "unpacking", dictionaries: "dictionaries", append: "append", sets: "sets",
    recursion: "recursion", "base case": "base cases", "call stack": "the call stack",
  },
  sk: {
    call: "príkazy", order: "poradie", comment: "poznámky", for: "cykly for", range: "range",
    variable: "premenné", update: "zmena premenných", text: "text", type: "typy",
    fstring: "f-reťazce", method: "príkazy textu", index: "výber písmen", if: "if",
    else: "else", elif: "elif", compare: "porovnávanie", and_or: "and / or", not: "not",
    sensor: "otázky na svet", debugging: "hľadanie chýb", while: "cykly while",
    break: "break", continue: "continue", "nested loops": "cykly v cykloch", variables: "premenné",
    def: "funkcie", parameters: "vstupy", defaults: "predvolené hodnoty", return: "return",
    import: "pomocné súbory", global: "global", try: "try", except: "except", ValueError: "ValueError",
    raise: "raise", assert: "assert", lists: "zoznamy", types: "typy", tuples: "n-tice",
    unpacking: "rozbaľovanie", dictionaries: "slovníky", append: "append", sets: "množiny",
    recursion: "rekurzia", "base case": "základné prípady", "call stack": "zásobník volaní",
  },
};

let current = "en";

function readSaved() {
  try {
    return localStorage.getItem(LANG_KEY);
  } catch {
    return null;
  }
}

export function initialLang() {
  const saved = readSaved();
  if (saved && saved in LANGS) return saved;
  const browser = (navigator.language || "en").slice(0, 2).toLowerCase();
  return browser in LANGS ? browser : "en";
}

export function setLang(lang) {
  current = lang in LANGS ? lang : "en";
  document.documentElement.lang = current;
  try {
    localStorage.setItem(LANG_KEY, current);
  } catch {
    // storage blocked: the browser language is used next time
  }
}

export function lang() {
  return current;
}

export function t(text, values = {}) {
  const template = (current === "sk" && SK[text]) || text;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in values ? values[key] : match));
}

export function concept(id) {
  return CONCEPTS[current]?.[id] || CONCEPTS.en[id] || id;
}

// Translate static markup: data-i18n (text), data-i18n-label (aria-label), data-i18n-title.
export function translatePage(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) {
    node.dataset.i18nKey ??= node.textContent.trim();
    node.textContent = t(node.dataset.i18nKey);
  }
  for (const node of root.querySelectorAll("[data-i18n-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  }
  for (const node of root.querySelectorAll("[data-i18n-title]")) {
    node.setAttribute("title", t(node.dataset.i18nTitle));
  }
}
