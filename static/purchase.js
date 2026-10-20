const detail = document.querySelector("[data-status-url]");
const code = document.querySelector("#token-code");
document.querySelector("#copy-code")?.addEventListener("click", async () => {
  const status = document.querySelector("#copy-status");
  try {
    await navigator.clipboard.writeText(code.textContent);
    status.textContent = "Copied. Keep your token code private.";
  } catch {
    status.textContent = "Select the code above and copy it manually.";
  }
});
if (detail && detail.dataset.orderStatus !== "paid") {
  let attempts = 0;
  const poll = async () => {
    attempts += 1;
    try {
      const response = await fetch(detail.dataset.statusUrl, {cache: "no-store"});
      if (response.status === 401) {
        document.querySelector("#payment-progress").textContent = "Please log in again to view your token code.";
        return;
      }
      if (response.ok) {
        const order = await response.json();
        if (order.status === "paid") {
          code.textContent = order.token_code;
          document.querySelector("#delivery").hidden = false;
          document.querySelector("#pending").hidden = true;
          document.querySelector("#order-status").textContent = "Delivered";
          return;
        }
      }
    } catch { /* A later poll can recover from a temporary connection failure. */ }
    if (attempts < 30) setTimeout(poll, 4000);
    else document.querySelector("#payment-progress").textContent = "Payment is still awaiting confirmation. You can return to this page later. If you have paid, do not pay again; contact the store with your purchase reference.";
  };
  setTimeout(poll, 2000);
}
