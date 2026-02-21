<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="logo">FIM Dataset Viewer</router-link>
    </header>
    <router-view />
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #1a1a2e;
  --bg-card: #16213e;
  --bg-sidebar: #0f3460;
  --text: #e0e0e0;
  --text-muted: #8899aa;
  --accent: #e94560;
  --accent-soft: rgba(233, 69, 96, 0.15);
  --middle-bg: rgba(233, 69, 96, 0.12);
  --middle-border: rgba(233, 69, 96, 0.3);
  --border: #2a2a4a;
  --code-bg: #0d1117;
  --success: #4caf50;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}

.app-header {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
}

.logo {
  color: var(--accent);
  text-decoration: none;
  font-weight: 700;
  font-size: 18px;
}

a { color: var(--accent); }

button {
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 14px;
}
button:hover { border-color: var(--accent); }

input, select {
  background: var(--code-bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 14px;
}
input:focus, select:focus { outline: none; border-color: var(--accent); }
</style>
