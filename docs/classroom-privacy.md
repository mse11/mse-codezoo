# CodeZoo in a classroom: what is stored, and where

This is a one-page note for schools, clubs and teachers who run CodeZoo's classroom hub (`codezoo class serve`). It describes how the software works. It is not legal advice and has not been through a formal privacy review yet (that review is the gate of phase 5 in [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)).

## In short

- **No cloud, no accounts.** The hub runs on the teacher's computer. Children's devices connect to it over the school's local network. Nothing is sent to the internet, and CodeZoo collects no analytics.
- **No email, password or birth date.** A child is a picture (one of 32 animals) and, only if the teacher allows it, a first name.
- **The school decides.** The data sits in a folder on the teacher's computer. The school (as data controller under GDPR) decides how long to keep it and who may see it.

## What the hub stores

For each class, in `<CodeZoo folder>/classes/<class id>/` on the teacher's computer:

| What | Why |
| --- | --- |
| Class name, type (workshop or class), settings, today's levels | To run the class |
| Each player's picture and name (a first name, or the picture's animal name) | To let the child find themselves again |
| Per level: stars, solved or not, number of tries, the best program, the date last played, kinds of mistakes (for example "loops that never stop") | Progress, the teacher's "who is stuck" view and the concept report |
| Minutes played per day | Shown to the teacher as "minutes today" |
| Programs and levels children shared, with the sharer's picture and name, and whether the teacher approved them | Sharing inside the class |
| The class's own levels | Levels the teacher added |

The CodeZoo folder is `%APPDATA%\CodeZoo` on Windows, `~/Library/Application Support/CodeZoo` on macOS and `~/.local/share/codezoo` on Linux, or the folder given with `codezoo class --data-dir`.

The hub does **not** store IP addresses, device names, photos or sound. While the hub runs, it remembers wrong class codes per device address in memory for five minutes (to slow down guessing), and forgets them when it stops.

On a child's device, the browser keeps the class code, which player was picked, the chosen language and the view settings. On the teacher's computer, the browser also keeps the teacher's key. A new hub start makes a new class code and a new teacher's key, so old ones stop working.

## Who can see what

- **The teacher's screen** needs the teacher's key, which is part of the address `codezoo class serve` prints in the terminal. Anyone with that address can see the class, so the teacher should not share or project it.
- **Children** with the class code see the list of players (pictures and names) and the shares the teacher approved. The game doesn't show them other children's progress. There are no per-child passwords, though: a child could tap a classmate's picture, and a child who knows the browser's developer tools could look up a classmate's stars. Treat progress as visible inside the class.
- **Anyone on the same network** who knows the hub's address but not the code sees only the class name and the empty game page.

The hub uses plain HTTP inside the local network, with no encryption. Run it only on a network the school trusts, not on public Wi-Fi.

## How long it is kept, and how to delete it

- **Workshop:** "End the workshop and delete its data" on the teacher's screen deletes the class folder. This is the default for workshops; save the class to a file first if you want to keep it.
- **Class:** the data stays until the teacher deletes it with `codezoo class delete NAME`.
- **One child:** "Remove" on the teacher's screen deletes that player and their progress.
- **Taking progress home:** "Take my progress home" (child) and "Save to a file" (teacher) create a JSON file with that child's progress. Whoever holds the file holds the data.

## Before using it with a class

- Tell parents what is stored (this page can help), following the school's own rules for learning tools.
- Turn "Children may type a first name" off when names aren't needed: children are then called after their picture ("Cat", "Cat 2"). Names are on by default since Nov 22, 2026, because several children may pick the same picture.
- Delete the data when a course ends.
