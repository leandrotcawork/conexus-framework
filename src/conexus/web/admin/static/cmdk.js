window.cmdkPalette = () => ({
  open: false, q: "",
  cmds: [
    { label: "Agents",      go: () => location.assign("/admin/") },
    { label: "Connectors",  go: () => location.assign("/admin/connectors") },
    { label: "Connections", go: () => location.assign("/admin/connections") },
    { label: "New agent",   go: () => location.assign("/admin/agents/new") },
  ],
  init() {
    window.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); this.open = !this.open; }
      if (e.key === "Escape") this.open = false;
    });
  },
  filtered() {
    const q = this.q.toLowerCase();
    return this.cmds.filter(c => c.label.toLowerCase().includes(q));
  },
});
