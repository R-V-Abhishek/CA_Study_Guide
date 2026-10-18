# Browser startup evidence

2026-10-17. Browser checks did not reach any application assertion.

## Headless Chromium

`FATAL:base/apple/mach_port_rendezvous_mac.cc:159` — `bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer...: unknown error code (141)`. Process exited with SIGTRAP.

## WebKit

`pw_run.sh: line 7: Abort trap: 6`. Process exited with code 134 before creating a page.

## Full Chromium fallback

# Error details

```
Error: browserType.launch: Target page, context or browser has been closed
Browser logs:

<launching> /Users/rva/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing --disable-field-trial-config --disable-background-networking --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-back-forward-cache --disable-breakpad --disable-client-side-phishing-detection --disable-component-extensions-with-background-pages --disable-component-update --no-default-browser-check --disable-default-apps --disable-dev-shm-usage --disable-edgeupdater --disable-extensions --disable-features=AvoidUnnecessaryBeforeUnloadCheckSync,DestroyProfileOnBrowserClose,DialMediaRouteProvider,GlobalMediaControls,HttpsUpgrades,LensOverlay,MediaRouter,PaintHolding,ThirdPartyStoragePartitioning,BlockOriginHeaderModificationOnRedirect,Translate,AutoDeElevate,OptimizationHints,msForceBrowserSignIn,msEdgeUpdateLaunchServicesPreferredVersion --enable-features=CDPScreenshotNewSurface --allow-pre-commit-input --disable-hang-monitor --disable-ipc-flooding-protection --disable-popup-blocking --disable-prompt-on-repost --disable-renderer-backgrounding --disable-updater-scheduler --force-color-profile=srgb --metrics-recording-only --no-first-run --password-store=basic --use-mock-keychain --no-service-autorun --export-tagged-pdf --disable-search-engine-choice-screen --unsafely-disable-devtools-self-xss-warnings --edge-skip-compat-layer-relaunch --disable-infobars --disable-search-engine-choice-screen --disable-sync --enable-unsafe-swiftshader --no-sandbox --user-data-dir=/var/folders/37/dbrwy0js4jq4q45z8djm3g580000gp/T/playwright_chromiumdev_profile-RujdTT --remote-debugging-pipe --no-startup-window
<launched> pid=88760
[pid=88760][err] [1017/104448.310048:ERROR:third_party/crashpad/crashpad/util/mach/bootstrap.cc:65] bootstrap_check_in org.chromium.crashpad.child_port_handshake.88778.15310614.YDCPPLPIDYUZVVTR: unknown error code (141)
[pid=88760][err] [1017/104448.311164:ERROR:third_party/crashpad/crashpad/util/file/file_io.cc:103] ReadExactly: expected 4, observed 0
[pid=88760][err] [1017/104448.312857:ERROR:third_party/crashpad/crashpad/util/mach/bootstrap.cc:65] bootstrap_check_in org.chromium.crashpad.child_port_handshake.88775.15310594.ZXRXMCDQYIVXUSEK: unknown error code (141)
[pid=88760][err] [1017/104448.313027:ERROR:third_party/crashpad/crashpad/util/file/file_io.cc:103] ReadExactly: expected 4, observed 0
[pid=88760][err] Received signal 6
[pid=88760][err]  [0x000124054588]
[pid=88760][err]  [0x0001289dbc88]
[pid=88760][err]  [0x0001823d5740]
[pid=88760][err]  [0x0001823cb8d4]
[pid=88760][err]  [0x0001822d1974]
[pid=88760][err]  [0x000189aa3d30]
[pid=88760][err]  [0x0001822294ac]
[pid=88760][err]  [0x00018221262c]
[pid=88760][err]  [0x000189a768c8]
[pid=88760][err]  [0x000189a766e4]
[pid=88760][err]  [0x000187871698]
[pid=88760][err]  [0x000187872338]
[pid=88760][err]  [0x0001878713c4]
[pid=88760][err]  [0x000187874868]
[pid=88760][err]  [0x000186890238]
[pid=88760][err]  [0x00018688e208]
[pid=88760][err]  [0x00018688dcfc]
[pid=88760][err]  [0x00012466e0d4]
[pid=88760][err]  [0x0001238a2b1c]
[pid=88760][err]  [0x0001238a2930]
[pid=88760][err]  [0x000122883080]
[pid=88760][err]  [0x000121fdd0cc]
[pid=88760][err]  [0x0001206094c0]
[pid=88760][err]  [0x000102c3080c]
[pid=88760][err]  [0x0001820004e0]
[pid=88760][err] [end of stack trace]
Call log:
  - <launching> /Users/rva/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing --disable-field-trial-config --disable-background-networking --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-back-forward-cache --disable-breakpad --disable-client-side-phishing-detection --disable-component-extensions-with-background-pages --disable-component-update --no-default-browser-check --disable-default-apps --disable-dev-shm-usage --disable-edgeupdater --disable-extensions --disable-features=AvoidUnnecessaryBeforeUnloadCheckSync,DestroyProfileOnBrowserClose,DialMediaRouteProvider,GlobalMediaControls,HttpsUpgrades,LensOverlay,MediaRouter,PaintHolding,ThirdPartyStoragePartitioning,BlockOriginHeaderModificationOnRedirect,Translate,AutoDeElevate,OptimizationHints,msForceBrowserSignIn,msEdgeUpdateLaunchServicesPreferredVersion --enable-features=CDPScreenshotNewSurface --allow-pre-commit-input --disable-hang-monitor --disable-ipc-flooding-protection --disable-popup-blocking --disable-prompt-on-repost --disable-renderer-backgrounding --disable-updater-scheduler --force-color-profile=srgb --metrics-recording-only --no-first-run --password-store=basic --use-mock-keychain --no-service-autorun --export-tagged-pdf --disable-search-engine-choice-screen --unsafely-disable-devtools-self-xss-warnings --edge-skip-compat-layer-relaunch --disable-infobars --disable-search-engine-choice-screen --disable-sync --enable-unsafe-swiftshader --no-sandbox --user-data-dir=/var/folders/37/dbrwy0js4jq4q45z8djm3g580000gp/T/playwright_chromiumdev_profile-RujdTT --remote-debugging-pipe --no-startup-window
  - <launched> pid=88760
  - [pid=88760][err] [1017/104448.310048:ERROR:third_party/crashpad/crashpad/util/mach/bootstrap.cc:65] bootstrap_check_in org.chromium.crashpad.child_port_handshake.88778.15310614.YDCPPLPIDYUZVVTR: unknown error code (141)
  - [pid=88760][err] [1017/104448.311164:ERROR:third_party/crashpad/crashpad/util/file/file_io.cc:103] ReadExactly: expected 4, observed 0
  - [pid=88760][err] [1017/104448.312857:ERROR:third_party/crashpad/crashpad/util/mach/bootstrap.cc:65] bootstrap_check_in org.chromium.crashpad.child_port_handshake.88775.15310594.ZXRXMCDQYIVXUSEK: unknown error code (141)
  - [pid=88760][err] [1017/104448.313027:ERROR:third_party/crashpad/crashpad/util/file/file_io.cc:103] ReadExactly: expected 4, observed 0
  - [pid=88760][err] Received signal 6
  - [pid=88760][err]  [0x000124054588]
  - [pid=88760][err]  [0x0001289dbc88]
  - [pid=88760][err]  [0x0001823d5740]
  - [pid=88760][err]  [0x0001823cb8d4]
  - [pid=88760][err]  [0x0001822d1974]
  - [pid=88760][err]  [0x000189aa3d30]
  - [pid=88760][err]  [0x0001822294ac]
  - [pid=88760][err]  [0x00018221262c]
  - [pid=88760][err]  [0x000189a768c8]
  - [pid=88760][err]  [0x000189a766e4]
  - [pid=88760][err]  [0x000187871698]
  - [pid=88760][err]  [0x000187872338]
  - [pid=88760][err]  [0x0001878713c4]
  - [pid=88760][err]  [0x000187874868]
  - [pid=88760][err]  [0x000186890238]
  - [pid=88760][err]  [0x00018688e208]
  - [pid=88760][err]  [0x00018688dcfc]
  - [pid=88760][err]  [0x00012466e0d4]
  - [pid=88760][err]  [0x0001238a2b1c]
  - [pid=88760][err]  [0x0001238a2930]
  - [pid=88760][err]  [0x000122883080]
  - [pid=88760][err]  [0x000121fdd0cc]
  - [pid=88760][err]  [0x0001206094c0]
  - [pid=88760][err]  [0x000102c3080c]
  - [pid=88760][err]  [0x0001820004e0]
  - [pid=88760][err] [end of stack trace]
  - [pid=88760] <gracefully close start>
  - [pid=88760] <kill>
  - [pid=88760] <will force kill>
  - [pid=88760] exception while trying to kill process: Error: kill EPERM
  - [pid=88760] <process did exit: exitCode=null, signal=SIGABRT>
  - [pid=88760] starting temporary directories cleanup
  - [pid=88760] finished temporary directories cleanup
  - [pid=88760] <gracefully close end>

```

## Computer-use fallback

Inventory returned no apps or browsers: `Sky Computer Use service startup request failed`. Creating an in-app browser tab returned `Browser is not available: iab`.
