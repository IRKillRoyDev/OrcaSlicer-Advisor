# OrcaSlicer Advisor

A Mac app that reads the OrcaSlicer profile you last saved, sends it to [Grok](https://grok.com) for a review, and writes accepted changes back as new user presets. The presets already in OrcaSlicer stay where they are.

Send to Grok is automatic. The app uses the Safari window you already have open, fills the prompt, submits it, and brings the reply back. If you are signed in, that happens in a background tab. If you are not, the tab comes forward so you can log in. You can still copy the JSON and paste it into Grok yourself.

The page is at `http://127.0.0.1:8777`. That address is whichever Mac is running the app, so another computer on the network cannot open it. Grok sign-in happens in Safari. This app does not store that password.

## What you do

1. Open **OrcaSlicer Advisor**. It starts the local page and opens it in a new Safari window.
2. Pick the printer setup. Brand, type, color, and diameter come from the filament profiles installed in OrcaSlicer.
3. Add part notes and load the STL. The part’s size goes into the JSON so Grok can work out supports and bridges. The Load STL button turns green when the file is valid.
4. Press Send to Grok. The app submits the JSON in Safari and returns the reply. Copy and paste still works if you want to send it yourself.
5. Paste Grok’s JSON response, name the preset after the part, preview the changes, and save.

New presets are named from the current profile plus that part name. Quit OrcaSlicer and open it again. They show up under User presets. Process and filament presets can be deleted from the User presets tab. Printer profiles and stock presets are left alone.

## Run it

The Dock app expects a virtualenv in this folder.

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
open "OrcaSlicer Advisor.app"
```

`Start OrcaSlicer Advisor.command` opens that same app. Quitting the app stops the local server.

Safari has to allow two things the first time:

- **System Settings → Privacy & Security → Automation:** Safari for OrcaSlicer Advisor. File → New Window uses this to open the page in its own Safari window.
- **Safari → Develop → Developer Settings:** Allow JavaScript from Apple Events. Send to Grok uses the Safari you already have open. A signed-in session runs in a background tab. Otherwise that tab comes forward so you can log in.

## What stays on your Mac

`work/` holds the loaded STL, server log, and page state. `venv/` is the local Python environment. Neither is in this repository. Logs are ignored too.

Settings are read from OrcaSlicer’s own config (`~/Library/Application Support/OrcaSlicer` on macOS) and from the profiles inside `/Applications/OrcaSlicer.app`. New preset files are written only under that config’s user preset folders.

## Develop

```bash
./venv/bin/uvicorn app:app --host 127.0.0.1 --port 8777
```

The Dock app is built from `launcher.applescript`. `boot-advisor.sh` starts the server. The icon source is `packaging/AppIcon.png`.

## License

MIT. See [LICENSE](LICENSE).
