# Browser surfaces

AgentOS treats the Codex in-app Browser and Google Chrome with the supported
Playwright Extension as separate browser surfaces.

## Selection

1. Follow an explicit user choice of browser, tab, URL or existing conversation.
2. Preserve an existing workstream binding when it still has the capability the
   task needs.
3. Without a narrower binding, use the in-app Browser for ordinary browsing,
   signed-in web work, short interactions and local web checks.
4. Use Chrome with the Playwright Extension when the task depends on existing
   Chrome state, a Chrome extension, a named persistent Chrome profile or an
   exact Chrome conversation.

There is no portable fallback order involving Safari, Yandex Browser,
Chromium-Gost or another local browser. A host or project may name one for a
specific workflow.

## Binding and evidence

Bind the selected browser, exact tab or conversation URL and required profile
before input, upload, download or submit. Recover a stale tab within the same
selected browser when possible. Change surfaces only after user direction or
current evidence that the required capability is unavailable.

For Chrome, attach the supported Playwright Extension to the intended tab.
Standalone Playwright, CDP discovery and native coordinate control are not
equivalent proof of an extension-bound session.

Browser selection changes transport only. It does not expand the task,
recipient, data scope, authentication rights or mutation authority. Report
untested capabilities as `NOT_TESTED`; do not infer them from another browser's
success or failure.

Host-specific profile paths, extension identifiers and versions belong in a
private host overlay. Do not publish or copy browser profiles or credentials.
