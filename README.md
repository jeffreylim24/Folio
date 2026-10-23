# Folio

Folio is a desktop app that helps you build and tailor your resume with the help of an AI model. It runs on macOS and Windows.

## Your data stays on your device

By default Folio runs an AI model on your own computer (through [Ollama](https://ollama.com)). Your resume and everything you type never leave your machine. Folio has no accounts and no telemetry.

The only times Folio uses the internet:

- To download and install Ollama and the AI model you pick.
- To talk to an AI provider, but only if you choose to use your own API key instead. In that case your text is sent to that provider, and you use it at your own risk.

If you use an API key, it is stored in your operating system's keychain, never in a plain file.

## Minimum requirements

To run the AI on your own computer you need:

- A Mac with 16 GB of memory, or on Windows either 16 GB of RAM or an NVIDIA graphics card with 8 GB. A Mac with 32 GB can run the best-quality model.
- About 6 GB of free disk space for the smallest model, and up to 26 GB for the largest.
- macOS or Windows.

Any computer that runs Folio can use your own API key instead.

Folio recommends a model that fits your computer and lets you pick a different one. Below these specs, Folio warns you before downloading, and the computer may become very slow or crash.

## Download and install

Get the latest installer from the [Releases page](https://github.com/jeffreylim24/Folio/releases):

- macOS: the `.dmg` file
- Windows: the `.exe` or `.msi` file

Folio is not code-signed yet, so your computer will warn you the first time. This is expected.

### macOS

1. Open the `.dmg` and drag Folio into Applications.
2. Open Folio from Applications. macOS says it can't verify the app; click **Done** (or **OK**).
3. Open **System Settings → Privacy & Security**, scroll down to the message about Folio, and click **Open Anyway**.
4. Confirm with **Open Anyway** and your password. You only need to do this once.

On macOS 14 or earlier you can instead right-click (or Control-click) Folio in Applications, choose **Open**, then click **Open** in the warning dialog.

### Windows

1. Run the installer.
2. When Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.

When Folio starts, the setup screen walks you through installing Ollama and choosing a model, or using an API key instead.

## For developers

Prerequisites: [uv](https://docs.astral.sh/uv/) (Python 3.13), Node.js 24, and [Rust](https://rustup.rs) (stable).

Layout: `engine/` is the Python backend, `app/` is the Tauri + React desktop shell, `scripts/` has build helpers.

Run in development:

```sh
scripts/build-engine.sh          # builds the engine sidecar into app/src-tauri/binaries/
cd app
npm ci
npm run tauri dev
```

Run tests:

```sh
cd engine && uv run pytest && uv run ruff check
cd app && npm test
cd app/src-tauri && cargo test   # needs the sidecar and `npm run build` first
```

Build an installer locally: `scripts/build-engine.sh && cd app && npm run tauri build`. The `.dmg` ends up in `app/src-tauri/target/release/bundle/dmg/`.

### CI

`.github/workflows/build.yml` runs the tests and builds installers for macOS and Windows, and uploads them as workflow artifacts. Pushing a `v*` tag also creates a draft GitHub release. On Windows it also runs `scripts/ci-windows-smoke.sh`, which starts the engine and runs the real Ollama silent installer.

### Testing on Windows

CI covers the engine and installer flags automatically. Before sharing a release, do one manual click-through on Windows (for example Windows 11 ARM in UTM on a Mac): install the `.exe` artifact, get past SmartScreen, and complete setup through to "You're all set".
