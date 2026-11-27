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

## Natural voices with Piper (optional)

Without recordings, read aloud and the animals' `say("...")` use the device's own voice. A
computer that runs `codezoo serve` can use a more natural one instead: the optional Piper
add-on, which makes the sound on that computer (nothing is sent anywhere).

1. Install Piper into the same Python as CodeZoo:

   ```
   uv pip install piper-tts
   ```

2. Put voice files in the `voices` folder of the CodeZoo folder (on Windows
   `%APPDATA%\CodeZoo\voices`, on macOS `~/Library/Application Support/CodeZoo/voices`, on
   Linux `~/.local/share/CodeZoo/voices`, or `$CODEZOO_HOME/voices`). Each voice is two
   files from https://huggingface.co/rhasspy/piper-voices, for example
   `sk_SK-lili-medium.onnx` and `sk_SK-lili-medium.onnx.json`. A voice serves the language
   its name starts with (`sk_`, `en_`, ...).

3. Restart `codezoo serve`. Languages without a Piper voice, the offline build and the
   classroom hub keep the device's voice.

Licenses: Piper is GPL-3.0; CodeZoo doesn't ship or depend on it, a grown-up adds it. Every
voice has its own license in its MODEL_CARD (the voice's training data, and the voice it was
fine-tuned from, if any): read it before you use a voice, especially outside the home or a
school. Some voices are for research and non-commercial use only (for example
`en_US-lessac`, trained on the Blizzard 2013 data): avoid those.

Voices we suggest (checked against their model cards):

| Language | Voice | Training data |
|---|---|---|
| Slovak | `sk_SK-lili-medium` (the only Slovak Piper voice) | Recordings CC0 ([OHF-Voice voice-datasets](https://github.com/OHF-Voice/voice-datasets)); fine-tuned from the `hifi_tts_92` base voice, trained on the [Hi-Fi TTS dataset](https://www.openslr.org/109/) (CC BY 4.0), see the attribution below |
| English | `en_US-ljspeech-medium` | [LJ Speech](https://keithito.com/LJ-Speech-Dataset/), public domain, trained from scratch |
| English | `en_US-kristin-medium` | LibriVox recordings, public domain, trained from scratch |
| English | `en_US-joe-medium` | CC0, fine-tuned from a CC0 base voice |

### Attribution

The Slovak voice `sk_SK-lili-medium` was fine-tuned from a base voice trained on the Hi-Fi
Multi-Speaker English TTS dataset (Hi-Fi TTS, reader 92, the voice of Cori Samuel) by
Evelina Bakhturina, Vitaly Lavrukhin, Boris Ginsburg and Yang Zhang (NVIDIA, 2021),
https://www.openslr.org/109/, licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). The voice files are not part of CodeZoo;
they are downloaded separately into the CodeZoo folder.
