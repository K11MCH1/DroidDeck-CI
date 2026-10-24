# DroidDeck-CI

Builds debug APKs of [K11MCH1/DroidDeck](https://github.com/K11MCH1/DroidDeck) and publishes each one as a
prerelease named after its source commit, for example `qualcomm-driver-d8d0b10`.

## When builds run

- **Poll DroidDeck branches** (`poll.yml`) runs hourly. It reads the heads of `main` and `qualcomm-driver`. When
  a head has no release here and no earlier build run, it starts **Build DroidDeck APK** for that exact commit.
  A failed commit is not retried automatically; run the build by hand to retry it.
- **Build DroidDeck APK** (`build.yml`) can also be started from the Actions tab with any branch, tag or commit SHA:

  ```bash
  gh workflow run build.yml -R K11MCH1/DroidDeck-CI -f ref=qualcomm-driver
  ```

GitHub disables scheduled workflows in a public repository after 60 days without repository activity. Re-enable
**Poll DroidDeck branches** on the Actions tab if that happens.

## What a build does

The steps mirror the `build` job of DroidDeck's own `.github/workflows/build.yml` (as of `qualcomm-driver`
`d8d0b10`), with a debug APK in place of the release APK:

1. **Linux runtime inputs.** The preloads, x86 preloads, Gamescope, uruntime, Mangoapp, PipeWire, msitools,
   droiddeck-esync packs, PulseAudio sink, DirectAudio and proot are built or fetched at their pinned checksums.
   Nothing is reused from a device.
2. **Add-on packs.** The Xbox backend is built on an ARM64 runner and the GOG companion is cross-compiled;
   `tools/packs/build.sh` then makes all five packs. The APK pins each pack's SHA-256 and downloads it from
   `Droid-Deck/DroidDeck-Components` under `pack-<name>-<sha>`, so the build fails if any pack is not published
   there. A fresh install could not download such a pack. The source is built under
   `/home/runner/work/DroidDeck/DroidDeck`, the path DroidDeck's own CI uses, because the Rust packs embed
   source paths and must come out byte-identical to the published ones.
3. **Rust store engines.** `libdroiddeckstores.so` is built with cargo-ndk (no `-PskipRust`), and
   `check_android_libraries.py` requires it in the APK.
4. **Qualcomm components**, for commits that have `tools/qualcomm/runtime.json`. The private Gamescope, Zink
   and WSI layer are built with `tools/qualcomm/build_{gamescope,zink,wsi}.py` in an Arch Linux ARM container on
   an ARM64 runner, the same distribution and GCC 16 series as the phone's proot build root.
   `ci/qualcomm/check_needed.py` fails the job if a binary needs a library the runtime lacks or a newer glibc
   than the phone build root offered. It also warns when a binary links different libraries than the phone
   build did. Results are cached by recipe, so commits that don't change `tools/qualcomm` reuse them.
5. **Pins.** `ci/qualcomm_pins.py` compares the CI-built files with the hashes in `runtime.json`; see below.
6. **APK.** `runtime_inputs.py record` and `verify`, `./gradlew :app:assembleDebug`, then
   `check_session_assets.py`, `runtime_inputs.py apk`, `check_android_libraries.py` and a testkey signature check.
   The default package is `com.droiddeck.launcher.xr` (input `app_id_suffix`), like the local dev builds.

## Qualcomm pins

`runtime.json` pins the phone-built Qualcomm binaries. Rebuilt in CI with another compiler build, another
source path and newer libraries, those binaries can come out different. The Mesa license files pinned on
`qualcomm-driver` also have CRLF line endings, which a Linux checkout does not reproduce. The `qualcomm_pins`
input chooses what happens then:

- `rebuild` (default): CI rewrites `runtime.json` in its own checkout to the hashes it built. That is the
  step `tools/qualcomm/README.md` prescribes after a deliberate rebuild. The runtime-input check then verifies
  that the APK holds exactly the files CI built. The release notes include a table of every file that
  differs, and the in-app build label says `Qualcomm re-pinned by CI`.
- `strict`: any difference fails the build, so only bit-identical phone builds are packaged.

Nothing is committed back to DroidDeck. To make CI's binaries the reference, copy the hashes from a release's
`qualcomm-pins.md` (or a `qualcomm-components` artifact's `build.json` files) into `runtime.json` there.

## Outputs

- A prerelease per commit holding `DroidDeck-<branch>-<sha7>-debug.apk`, `SHA256SUMS` and `build-info.json`.
  The newest 15 per branch are kept (repository variable `KEEP_RELEASES`).
- The same files as a 30-day workflow artifact `DroidDeck-<branch>-<sha7>-debug`.

APKs are signed with the public AOSP testkey, like local debug builds, so one installs over a local debug
build of the same package.

## Settings

Repository variables (Settings → Secrets and variables → Actions → Variables), all optional:

| Variable | Default |
| --- | --- |
| `DROIDDECK_REPO` | `K11MCH1/DroidDeck` |
| `DROIDDECK_BRANCHES` | `main qualcomm-driver` |
| `KEEP_RELEASES` | `15` |

No secrets are needed: DroidDeck and every input are public.

## Keeping in step with DroidDeck

When DroidDeck changes how its runtime inputs are prepared (new steps in its `build.yml`, new entries in
`tools/release/runtime_inputs.py`), the matching step has to be added to `build.yml` here. Until then
`runtime_inputs.py record` fails with the missing input's name.
