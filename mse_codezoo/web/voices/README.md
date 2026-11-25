# Recorded voices

Read aloud uses the device's own speech voice. A recorded voice can replace it, sentence by
sentence: a sentence that has a recording plays it, every other one is still spoken by the
device.

## Adding recordings

1. Record the sentence exactly as the page says it (a goal, a hint, a block's meaning, a
   feeling after a run). Short files: mono, 48 kHz or less, MP3 or OGG, quiet room, no music.
2. Put the file in the language's folder, for example `voices/sk/goal-bananas.mp3` (file
   names: letters, digits, `-`, `_`, `.`).
3. Add it to that folder's `manifest.json`: the sentence as the page shows it, mapped to the
   file name:

   ```json
   {
     "Pomôž opičke pozbierať všetky banány.": "goal-bananas.mp3"
   }
   ```

Emoji and stars are left out of what is spoken, so leave them out of the sentence too. The
offline build (`codezoo build-web`) copies the recordings with everything else.

Recordings are made by people: ask a child-friendly native speaker, get written consent for
using their voice, and note it in `voices/<lang>/CREDITS.md`.
