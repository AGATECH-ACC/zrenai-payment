let checkoutScript;
function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (!checkoutScript) {
    checkoutScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => window.Razorpay ? resolve() : reject(new Error("支付暂不可用。"));
      script.onerror = () => {
        script.remove();
        checkoutScript = null;
        reject(new Error("支付页面加载失败，请检查网络连接。"));
      };
      document.head.appendChild(script);
    });
  }
  return checkoutScript;
}
document.querySelectorAll(".buy-button").forEach(button => {
  button.addEventListener("click", async () => {
    const message = document.querySelector("#checkout-message");
    const original = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "正在准备支付…";
    message.hidden = true;
    try {
      await loadCheckout();
      const response = await fetch(button.dataset.endpoint || "/api/checkout/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value
        },
        body: JSON.stringify(button.dataset.product ? {product_id: Number(button.dataset.product)} : {})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "无法发起支付。");
      if (!data.checkout) {
        location.assign(data.purchase_url);
        return;
      }
      const checkout = new window.Razorpay({
        ...data.checkout,
        modal: {ondismiss() {
          message.textContent = "支付窗口已关闭。您可在购买记录中继续支付或查看订单状态。";
          message.hidden = false;
        }}
      });
      checkout.open();
    } catch (error) {
      message.textContent = error.message || "支付暂不可用，请重试。";
      message.hidden = false;
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.innerHTML = original;
    }
  });
});
