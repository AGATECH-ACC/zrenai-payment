const detail = document.querySelector("[data-status-url]");
const code = document.querySelector("#token-code");
document.querySelector("#copy-code")?.addEventListener("click", async () => {
  const status = document.querySelector("#copy-status");
  try {
    await navigator.clipboard.writeText(code.textContent);
    status.textContent = "已复制，请妥善保管您的兑换码。";
    window.ZrenUI?.notify("兑换码已复制。");
  } catch {
    status.textContent = "请选中上方兑换码并手动复制。";
  }
});
if (detail && detail.dataset.orderStatus !== "paid") {
  let attempts = 0;
  const poll = async () => {
    attempts += 1;
    try {
      const response = await fetch(detail.dataset.statusUrl, {cache: "no-store"});
      if (response.status === 401) {
        document.querySelector("#payment-progress").textContent = "请重新登录后查看兑换码。";
        document.querySelector("#payment-loading").hidden = true;
        return;
      }
      if (response.ok) {
        const order = await response.json();
        if (order.status === "paid") {
          code.textContent = order.token_code;
          document.querySelector("#delivery").hidden = false;
          document.querySelector("#pending").hidden = true;
          document.querySelector("#order-status").innerHTML = '<span class="zr-badge zr-badge--success">已交付</span>';
          document.querySelector("#pending")?.setAttribute("aria-busy", "false");
          return;
        }
      }
    } catch { /* A later poll can recover from a temporary connection failure. */ }
    if (attempts < 30) setTimeout(poll, 4000);
    else {
      document.querySelector("#payment-loading").hidden = true;
      document.querySelector("#payment-progress").textContent = "支付仍在等待确认，您可以稍后返回查看。如已付款，请勿重复支付；请提供订单编号联系店主。";
    }
  };
  setTimeout(poll, 2000);
}
