// Reads/writes server display state. The write token is injected on window by
// the page (the wall page has no token; only /control does — see Task 7).
export async function getDisplay() {
  try { return await (await fetch("/api/display")).json(); }
  catch (e) { return null; }
}

export async function patchDisplay(fields) {
  const token = window.__VIZ_TOKEN__ || "";
  try {
    return await (await fetch("/api/display", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Dashboard-Token": token },
      body: JSON.stringify(fields),
    })).json();
  } catch (e) { return null; }
}
