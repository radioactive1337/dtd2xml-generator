<template>
  <div class="app">
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">XML</span>
        <span class="logo-text">QA XML Generator</span>
      </div>
      <nav class="nav">
        <router-link to="/" class="nav-link">Generator</router-link>
        <router-link to="/settings" class="nav-link">Settings</router-link>
      </nav>
    </header>
    <main class="app-main">
      <div class="route-wrapper">
        <router-view />
      </div>
    </main>
  </div>
</template>

<style scoped>
.app {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  background: var(--accent);
  color: white;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 4px;
}

.logo-text {
  font-weight: 600;
  font-size: 16px;
}

.nav {
  display: flex;
  gap: 8px;
}

.nav-link {
  color: var(--text-muted);
  text-decoration: none;
  padding: 6px 14px;
  border-radius: var(--radius);
  font-size: 14px;
  transition: all 0.15s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: var(--text);
  background: var(--surface2);
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
}

.route-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
